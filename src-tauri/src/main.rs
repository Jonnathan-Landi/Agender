#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    io::{BufRead, BufReader},
    net::TcpStream,
    process::{Child, Command, Stdio},
    sync::mpsc,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::Manager;
use tauri_plugin_updater::UpdaterExt;

const BACKEND_PORT_PREFIX: &str = "AGENDER_BACKEND_PORT=";
const BACKEND_START_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct UpdateInfo {
    current_version: String,
    version: String,
    date: Option<String>,
    body: Option<String>,
}

#[derive(Default)]
struct UpdateDownload {
    phase: String,
    version: String,
    downloaded: u64,
    total: Option<u64>,
    bytes: Option<Vec<u8>>,
}

struct UpdateState(Arc<Mutex<UpdateDownload>>);
struct TrustedBackend(Arc<Mutex<Option<u16>>>);
struct BackgroundMode(AtomicBool);

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn ensure_trusted_window(
    window: &tauri::WebviewWindow,
    trusted: &TrustedBackend,
) -> Result<(), String> {
    let expected_port = *trusted
        .0
        .lock()
        .map_err(|_| "Estado de seguridad no disponible")?;
    let url = window.url().map_err(|error| error.to_string())?;
    if url.scheme() == "http" && url.host_str() == Some("127.0.0.1") && url.port() == expected_port
    {
        Ok(())
    } else {
        Err("Origen de la ventana no autorizado".into())
    }
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct UpdateDownloadStatus {
    phase: String,
    version: String,
    downloaded: u64,
    total: Option<u64>,
    percent: Option<u8>,
}

fn update_status(state: &UpdateState) -> UpdateDownloadStatus {
    let download = state.0.lock().unwrap();
    UpdateDownloadStatus {
        phase: if download.phase.is_empty() {
            "idle".into()
        } else {
            download.phase.clone()
        },
        version: download.version.clone(),
        downloaded: download.downloaded,
        total: download.total,
        percent: download
            .total
            .filter(|total| *total > 0)
            .map(|total| ((download.downloaded.saturating_mul(100) / total).min(100)) as u8),
    }
}

#[tauri::command]
fn set_background_mode(
    enabled: bool,
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    trusted: tauri::State<'_, TrustedBackend>,
    state: tauri::State<'_, BackgroundMode>,
) -> Result<(), String> {
    ensure_trusted_window(&window, &trusted)?;
    state.0.store(enabled, Ordering::Relaxed);
    if let Some(tray) = app.tray_by_id("agender") {
        tray.set_visible(enabled)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn check_for_update(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    trusted: tauri::State<'_, TrustedBackend>,
) -> Result<Option<UpdateInfo>, String> {
    ensure_trusted_window(&window, &trusted)?;
    let update = app
        .updater()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?;

    Ok(update.map(|update| UpdateInfo {
        current_version: update.current_version,
        version: update.version,
        date: update.date.map(|date| date.to_string()),
        body: update.body,
    }))
}

#[tauri::command]
fn get_update_download_status(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, UpdateState>,
    trusted: tauri::State<'_, TrustedBackend>,
) -> Result<UpdateDownloadStatus, String> {
    ensure_trusted_window(&window, &trusted)?;
    Ok(update_status(&state))
}

#[tauri::command]
async fn download_update(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, UpdateState>,
    trusted: tauri::State<'_, TrustedBackend>,
) -> Result<UpdateDownloadStatus, String> {
    ensure_trusted_window(&window, &trusted)?;
    let update = app
        .updater()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?
        .ok_or_else(|| "No hay una actualización disponible.".to_string())?;

    let already_downloaded = {
        let mut download = state.0.lock().unwrap();
        if download.phase == "downloading" {
            return Err("La actualización ya se está descargando.".into());
        }
        if download.phase == "ready" && download.version == update.version {
            true
        } else {
            *download = UpdateDownload {
                phase: "downloading".into(),
                version: update.version.clone(),
                ..Default::default()
            };
            false
        }
    };
    if already_downloaded {
        return Ok(update_status(&state));
    }

    let progress = state.0.clone();
    let bytes = update
        .download(
            move |chunk_length, content_length| {
                let mut download = progress.lock().unwrap();
                download.downloaded = download.downloaded.saturating_add(chunk_length as u64);
                download.total = content_length;
            },
            || {},
        )
        .await;

    match bytes {
        Ok(bytes) => {
            let mut download = state.0.lock().unwrap();
            download.downloaded = download.total.unwrap_or(bytes.len() as u64);
            download.bytes = Some(bytes);
            download.phase = "ready".into();
            drop(download);
            Ok(update_status(&state))
        }
        Err(error) => {
            state.0.lock().unwrap().phase = "failed".into();
            Err(error.to_string())
        }
    }
}

#[tauri::command]
async fn install_update(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, UpdateState>,
    trusted: tauri::State<'_, TrustedBackend>,
) -> Result<(), String> {
    ensure_trusted_window(&window, &trusted)?;
    let expected_version = {
        let download = state.0.lock().unwrap();
        if download.phase != "ready" || download.bytes.is_none() {
            return Err("Primero descarga completamente la actualización.".into());
        }
        download.version.clone()
    };
    let update = app
        .updater()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?
        .filter(|update| update.version == expected_version)
        .ok_or_else(|| "La actualización descargada ya no está disponible.".to_string())?;
    let bytes = {
        let mut download = state.0.lock().unwrap();
        download.phase = "installing".into();
        download.bytes.take().unwrap()
    };

    stop_backend(&app);
    update.install(bytes).map_err(|error| error.to_string())?;
    app.restart();
}

struct BackendProcess(Arc<Mutex<Option<Child>>>);

fn stop_backend(app: &tauri::AppHandle) {
    if let Some(mut child) = app.state::<BackendProcess>().0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn announced_backend_port(child: &mut Child) -> Result<u16, Box<dyn std::error::Error>> {
    let stdout = child
        .stdout
        .take()
        .ok_or("No se pudo leer el puerto del backend.")?;
    let (sender, receiver) = mpsc::channel();

    thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(stdout).read_line(&mut line).map(|_| line);
        let _ = sender.send(result);
    });

    let line = receiver
        .recv_timeout(BACKEND_START_TIMEOUT)
        .map_err(|_| "El backend agotó el tiempo máximo de arranque.")??;
    let port = line
        .trim()
        .strip_prefix(BACKEND_PORT_PREFIX)
        .ok_or("El backend devolvió una respuesta de arranque inválida.")?
        .parse::<u16>()?;

    if port == 0 {
        return Err("El backend devolvió un puerto inválido.".into());
    }
    Ok(port)
}

fn main() {
    let backend = BackendProcess(Arc::new(Mutex::new(None)));
    let backend_for_exit = backend.0.clone();
    let updater = UpdateState(Arc::new(Mutex::new(UpdateDownload::default())));
    let trusted_backend = TrustedBackend(Arc::new(Mutex::new(None)));
    let navigation_port = trusted_backend.0.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(
            |app, _arguments, _working_directory| {
                show_main_window(app);
            },
        ))
        .plugin(
            tauri::plugin::Builder::<tauri::Wry, ()>::new("navigation-guard")
                .on_navigation(move |_webview, url| {
                    if url.scheme() == "tauri" {
                        return true;
                    }
                    let expected_port = navigation_port.lock().ok().and_then(|port| *port);
                    url.scheme() == "http"
                        && url.host_str() == Some("127.0.0.1")
                        && url.port() == expected_port
                })
                .build(),
        )
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            check_for_update,
            get_update_download_status,
            download_update,
            install_update,
            set_background_mode
        ])
        .manage(backend)
        .manage(updater)
        .manage(trusted_backend)
        .manage(BackgroundMode(AtomicBool::new(false)))
        .setup(|app| {
            if let Some(icon) = app.default_window_icon().cloned() {
                let tray = TrayIconBuilder::with_id("agender")
                    .icon(icon)
                    .tooltip("Agender")
                    .show_menu_on_left_click(false)
                    .on_tray_icon_event(|tray, event| {
                        if matches!(
                            event,
                            TrayIconEvent::Click {
                                button: MouseButton::Left,
                                button_state: MouseButtonState::Up,
                                ..
                            } | TrayIconEvent::DoubleClick {
                                button: MouseButton::Left,
                                ..
                            }
                        ) {
                            show_main_window(tray.app_handle());
                        }
                    })
                    .build(app)?;
                tray.set_visible(false)?;
            }
            if let Some(window) = app.get_webview_window("main") {
                let close_handle = app.handle().clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                        if close_handle
                            .state::<BackgroundMode>()
                            .0
                            .load(Ordering::Relaxed)
                        {
                            api.prevent_close();
                            if let Some(window) = close_handle.get_webview_window("main") {
                                let _ = window.hide();
                            }
                        } else {
                            stop_backend(&close_handle);
                        }
                    }
                });
            }
            #[cfg(debug_assertions)]
            let mut command = {
                let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                    .parent()
                    .unwrap();
                let virtualenv_python = project_root
                    .join(".venv")
                    .join("Scripts")
                    .join("python.exe");
                let python = if virtualenv_python.is_file() {
                    virtualenv_python.into_os_string()
                } else {
                    "python".into()
                };
                let mut command = Command::new(python);
                command.current_dir(project_root).args([
                    "-m",
                    "backend",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "47831",
                ]);
                command
            };

            #[cfg(not(debug_assertions))]
            let mut command = {
                let executable = app
                    .path()
                    .resource_dir()?
                    .join("backend")
                    .join("agender-backend.exe");
                let mut command = Command::new(executable);
                command.args(["--host", "127.0.0.1", "--port", "47831"]);
                command
            };

            command.stdin(Stdio::null()).stdout(Stdio::piped());

            #[cfg(debug_assertions)]
            command.stderr(Stdio::inherit());

            #[cfg(not(debug_assertions))]
            command.stderr(Stdio::null());

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                command.creation_flags(0x08000000);
            }

            let mut child = command.spawn()?;
            let port = match announced_backend_port(&mut child) {
                Ok(port) => port,
                Err(error) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(error);
                }
            };
            app.state::<BackendProcess>()
                .0
                .lock()
                .unwrap()
                .replace(child);
            *app.state::<TrustedBackend>().0.lock().unwrap() = Some(port);

            let handle = app.handle().clone();
            thread::spawn(move || {
                let address = format!("127.0.0.1:{port}");
                let ready = (0..240).any(|_| {
                    if TcpStream::connect(&address).is_ok() {
                        true
                    } else {
                        thread::sleep(Duration::from_millis(50));
                        false
                    }
                });

                if ready {
                    let cache_buster = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map(|duration| duration.as_millis())
                        .unwrap_or_default();
                    let url = format!("http://{address}/?t={cache_buster}")
                        .parse()
                        .unwrap();
                    let window_handle = handle.clone();
                    let _ = handle.run_on_main_thread(move || {
                        if let Some(window) = window_handle.get_webview_window("main") {
                            let _ = window.navigate(url);
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    });
                } else {
                    handle.exit(1);
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("No fue posible iniciar Agender")
        .run(move |app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                // tray-icon 0.24 removes hidden Windows icons when hiding them
                // and then attempts NIM_DELETE again during Drop. Registering it
                // immediately before teardown makes that final cleanup valid.
                if let Some(tray) = app.tray_by_id("agender") {
                    let _ = tray.set_visible(true);
                }
            }
            if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
                if let Some(mut child) = backend_for_exit.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}

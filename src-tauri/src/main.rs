#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    net::{TcpListener, TcpStream},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};
use tauri::Manager;
use tauri_plugin_updater::UpdaterExt;

const BACKEND_PORT: u16 = 47831;

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct UpdateInfo {
    current_version: String,
    version: String,
    date: Option<String>,
    body: Option<String>,
}

#[tauri::command]
async fn check_for_update(app: tauri::AppHandle) -> Result<Option<UpdateInfo>, String> {
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
async fn install_update(app: tauri::AppHandle) -> Result<(), String> {
    let update = app
        .updater()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?
        .ok_or_else(|| "No hay una actualización disponible.".to_string())?;

    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|error| error.to_string())?;
    app.restart();
}

struct BackendProcess(Arc<Mutex<Option<Child>>>);

fn backend_port() -> Result<u16, Box<dyn std::error::Error>> {
    // Un origen HTTP estable conserva localStorage entre reinicios y actualizaciones.
    let listener = TcpListener::bind(("127.0.0.1", BACKEND_PORT))?;
    drop(listener);
    Ok(BACKEND_PORT)
}

fn main() {
    let backend = BackendProcess(Arc::new(Mutex::new(None)));
    let backend_for_exit = backend.0.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![check_for_update, install_update])
        .manage(backend)
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let close_handle = app.handle().clone();
                window.on_window_event(move |event| {
                    if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                        if let Some(mut child) = close_handle
                            .state::<BackendProcess>()
                            .0
                            .lock()
                            .unwrap()
                            .take()
                        {
                            let _ = child.kill();
                        }
                        close_handle.exit(0);
                    }
                });
            }
            let port = backend_port()?;
            #[cfg(debug_assertions)]
            let mut command = {
                let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
                let mut command = Command::new("python");
                command.current_dir(project_root).args(["-m", "backend", "--host", "127.0.0.1", "--port", &port.to_string()]);
                command
            };

            #[cfg(not(debug_assertions))]
            let mut command = {
                let executable = app.path().resource_dir()?.join("backend").join("agender-backend.exe");
                let mut command = Command::new(executable);
                command.args(["--host", "127.0.0.1", "--port", &port.to_string()]);
                command
            };

            command
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                command.creation_flags(0x08000000);
            }

            let child = command.spawn()?;
            app.state::<BackendProcess>().0.lock().unwrap().replace(child);

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
                    let url = format!("http://{address}").parse().unwrap();
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
        .run(move |_app, event| {
            if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
                if let Some(mut child) = backend_for_exit.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}

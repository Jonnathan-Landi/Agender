fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "check_for_update",
            "get_update_download_status",
            "download_update",
            "install_update",
            "set_background_mode",
        ]),
    ))
    .expect("No fue posible generar el manifiesto de Tauri");
}

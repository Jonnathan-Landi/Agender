fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(
            tauri_build::AppManifest::new()
                .commands(&["check_for_update", "install_update"]),
        ),
    )
    .expect("No fue posible generar el manifiesto de Tauri");
}

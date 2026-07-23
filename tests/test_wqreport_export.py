import json
import unittest
from pathlib import Path

from backend.main import app
from backend.user_data import _allowed_keys, syncable_data_keys
from backend.wqreport_export import (
    REPORT_MIN_HEIGHT,
    REPORT_WIDTH,
    _build_print_document,
    _safe_file_name,
    _sanitize_report_html,
)


class WaterQualityReportExportTests(unittest.TestCase):
    def test_file_name_is_safe_and_keeps_report_date(self):
        self.assertEqual(_safe_file_name("Reporte_CA_19072026"), "Reporte_CA_19072026")
        self.assertEqual(_safe_file_name('../Reporte:"CA"?'), "..ReporteCA")

    def test_unsafe_embedded_content_is_removed(self):
        source = '<section onclick="bad()"><script>alert(1)</script><p>Reporte</p></section>'
        sanitized = _sanitize_report_html(source)
        self.assertNotIn("script", sanitized.lower())
        self.assertNotIn("onclick", sanitized.lower())
        self.assertIn("<p>Reporte</p>", sanitized)

    def test_print_document_uses_original_wqreport_dimensions(self):
        document = _build_print_document(
            '<div id="reports"><section class="report-page">Página</section></div>',
            REPORT_MIN_HEIGHT,
            "http://127.0.0.1:47831/wqreport/",
        )
        self.assertIn(f"width: {REPORT_WIDTH}px", document)
        self.assertIn(f"height: {REPORT_MIN_HEIGHT}px", document)
        self.assertIn("@page", document)
        self.assertIn("print-color-adjust: exact", document)


class WaterQualityReportIntegrationTests(unittest.TestCase):
    def test_static_application_is_mounted(self):
        mounts = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/assets", mounts)
        self.assertIn("/wqreport", mounts)

    def test_heavy_basin_catalog_is_loaded_only_for_hydromet(self):
        project_root = Path(__file__).resolve().parent.parent
        document = (project_root / "frontend" / "index.html").read_text(encoding="utf-8")
        application = (project_root / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('<script src="js/subcuencas-data.js"></script>', document)
        self.assertIn('if (modules.has("hydromet"))', application)
        self.assertIn('loadScriptOnce("js/subcuencas-data.js")', application)

    def test_sync_refreshes_data_without_reloading_the_application(self):
        project_root = Path(__file__).resolve().parent.parent
        navigation = (
            project_root / "frontend" / "js" / "core" / "navigation.js"
        ).read_text(encoding="utf-8")
        synchronization = (
            project_root / "frontend" / "js" / "core" / "sync.js"
        ).read_text(encoding="utf-8")
        storage = (
            project_root / "frontend" / "js" / "core" / "storage.js"
        ).read_text(encoding="utf-8")
        self.assertIn('const ACTIVE_VIEW_KEY = "agender.navigation.active-view"', navigation)
        self.assertIn("sessionStorage.setItem(ACTIVE_VIEW_KEY, viewName)", navigation)
        self.assertIn("restoreActiveView();", navigation)
        self.assertIn("window.NotasStorage.refreshFromServer()", synchronization)
        self.assertNotIn("location.reload()", synchronization)
        self.assertNotIn("scheduleReload", synchronization)
        self.assertIn('new CustomEvent("agender:data-refreshed"', storage)
        self.assertIn("readLocal(pendingKey(key)).found", storage)

    def test_license_generator_is_a_full_view_without_legacy_dialog(self):
        project_root = Path(__file__).resolve().parent.parent
        document = (project_root / "frontend" / "index.html").read_text(encoding="utf-8")
        controller = (
            project_root / "frontend" / "js" / "core" / "license-admin.js"
        ).read_text(encoding="utf-8")
        self.assertIn('data-view="license-admin"', document)
        self.assertIn('class="view license-admin-view"', document)
        self.assertNotIn('id="license-admin-dialog"', document)
        self.assertNotIn("dialog.showModal()", controller)
        self.assertNotIn("dialog.close()", controller)

    def test_release_versions_are_aligned(self):
        project_root = Path(__file__).resolve().parent.parent
        tauri_config = json.loads(
            (project_root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
        )
        cargo_manifest = (
            project_root / "src-tauri" / "Cargo.toml"
        ).read_text(encoding="utf-8")
        viewer_api = (
            project_root / "backend" / "viewer" / "api.py"
        ).read_text(encoding="utf-8")
        document = (project_root / "frontend" / "index.html").read_text(encoding="utf-8")
        version = tauri_config["version"]
        self.assertIn(f'version = "{version}"', cargo_manifest)
        self.assertIn(f'version="{version}"', viewer_api)
        self.assertIn(f"Novedades de Agender {version}", document)

    def test_report_storage_requires_water_quality_submodule(self):
        user = {"modules": ["report-water-quality"]}
        keys = _allowed_keys(user)
        self.assertIn("agender.reports.water-quality", keys)
        self.assertIn("agender.reports.water-quality.preferences", keys)
        self.assertNotIn(
            "agender.reports.water-quality",
            _allowed_keys({"modules": ["report-hydromet-network"]}),
        )
        self.assertNotIn("agender.reports.water-quality", _allowed_keys({"modules": []}))

    def test_report_storage_is_excluded_from_onedrive(self):
        keys = syncable_data_keys({"modules": ["report-water-quality"]})
        self.assertNotIn("agender.reports.water-quality", keys)
        self.assertNotIn("agender.reports.water-quality.preferences", keys)

    def test_report_license_exposes_both_submodules(self):
        project_root = Path(__file__).resolve().parent.parent
        document = (project_root / "frontend" / "index.html").read_text(encoding="utf-8")
        controller = (
            project_root / "frontend" / "js" / "core" / "license-admin.js"
        ).read_text(encoding="utf-8")
        self.assertIn('id="license-reports-all"', document)
        self.assertIn('value="report-water-quality"', document)
        self.assertIn('value="report-hydromet-network"', document)
        self.assertIn("setupPermissionGroup(reportsAll, reportModules)", controller)

    def test_report_only_persists_from_manual_save(self):
        project_root = Path(__file__).resolve().parent.parent
        controller = (
            project_root / "frontend" / "js" / "features" / "water-quality-report.js"
        ).read_text(encoding="utf-8")
        self.assertIn('addEventListener("click", async () =>', controller)
        self.assertIn("await bridge.save()", controller)
        self.assertIn("{ notify: false }", controller)
        self.assertNotIn("savePreferencesIfChanged", controller)

    def test_first_page_tlp_is_propagated_to_following_pages(self):
        project_root = Path(__file__).resolve().parent.parent
        events = (
            project_root / "frontend" / "wqreport" / "js" / "events.js"
        ).read_text(encoding="utf-8")
        main = (
            project_root / "frontend" / "wqreport" / "js" / "main.js"
        ).read_text(encoding="utf-8")
        self.assertIn("export function initializeTlpControls()", events)
        self.assertIn('document.querySelectorAll(".ti-header-tlp-select")', events)
        self.assertIn("tlpSelects.slice(1)", events)
        self.assertIn("select.value = this.value", events)
        self.assertIn("initializeTlpControls();", main)

    def test_report_zoom_batches_layout_work(self):
        project_root = Path(__file__).resolve().parent.parent
        zoom = (
            project_root / "frontend" / "wqreport" / "js" / "report-zoom.js"
        ).read_text(encoding="utf-8")
        self.assertIn("function scheduleReportsFit()", zoom)
        self.assertIn("if (pendingFitFrame) return", zoom)
        self.assertIn('addEventListener("resize", scheduleReportsFit)', zoom)

    def test_embedded_document_has_no_electron_shell(self):
        project_root = Path(__file__).resolve().parent.parent
        document = (project_root / "frontend" / "wqreport" / "index.html").read_text(encoding="utf-8")
        self.assertIn("js/agender-bridge.js", document)
        self.assertNotIn("titlebar.js", document)
        self.assertNotIn("settings-view", document)
        self.assertNotIn("electronAPI", document)

    def test_embedded_viewer_has_no_obsolete_window_shell(self):
        project_root = Path(__file__).resolve().parent.parent
        viewer_root = project_root / "frontend" / "viewer"
        document = (viewer_root / "index.html").read_text(encoding="utf-8")
        controller = (viewer_root / "app.js").read_text(encoding="utf-8")
        styles = (viewer_root / "styles.css").read_text(encoding="utf-8")
        for obsolete in ("settingsFlyout", "windowCloseBtn", "embedded-viewer"):
            self.assertNotIn(obsolete, document)
            self.assertNotIn(obsolete, controller)
            self.assertNotIn(obsolete, styles)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]


class HydrometReportIntegrationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        cls.app = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "frontend/css/hydromet-report.css").read_text(encoding="utf-8")
        cls.feature = (ROOT / "frontend/js/features/hydromet-report.js").read_text(encoding="utf-8")
        cls.export_feature = (
            ROOT / "frontend/js/features/hydromet-design-export.js"
        ).read_text(encoding="utf-8")

    def test_navigation_places_hydromet_report_below_water_quality(self) -> None:
        water_quality = self.document.index('data-view="report-water-quality"')
        hydromet_report = self.document.index('data-view="report-hydromet-network"')

        self.assertLess(water_quality, hydromet_report)
        self.assertIn('<span class="nav-label">Red hidrometeorológica</span>', self.document)

    def test_report_layers_are_stacked_in_the_expected_order(self) -> None:
        expected = (
            "01-caudales.jpeg",
            "02-lluvias.jpeg",
            "03-temperaturas.jpeg",
            "04-pronostico-diario.jpeg",
            "05-pronostico-semanal.jpeg",
            "06-indice-ultravioleta.jpeg",
        )
        positions = [self.document.index(name) for name in expected]

        self.assertEqual(positions, sorted(positions))
        self.assertIn(".hydromet-report-stack", self.styles)
        self.assertIn("display: grid", self.styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", self.styles)
        self.assertIn("@media (max-width: 760px)", self.styles)

    def test_every_report_layer_is_packaged_as_a_frontend_asset(self) -> None:
        assets = ROOT / "frontend/assets/hydromet-report"

        self.assertEqual(6, len(list(assets.glob("*.jpeg"))))
        self.assertTrue(all(path.stat().st_size > 0 for path in assets.glob("*.jpeg")))

    def test_module_style_is_loaded_only_with_its_permission(self) -> None:
        self.assertIn('modules.has("report-hydromet-network")', self.app)
        self.assertIn('loadStyleOnce("css/hydromet-report.css")', self.app)
        export_loader = 'loadScriptOnce("js/features/hydromet-design-export.js")'
        report_loader = 'loadScriptOnce("js/features/hydromet-report.js")'
        self.assertLess(self.app.index(export_loader), self.app.index(report_loader))
        self.assertIn(f"{export_loader}\n        .then(() => {report_loader})", self.app)
        self.assertIn('loadScriptOnce("js/features/hydromet-report.js")', self.app)
        self.assertIn("window.NotasHydrometReport.init()", self.app)

    def test_only_forecast_and_uv_formats_have_editable_image_areas(self) -> None:
        self.assertEqual(3, self.document.count('class="hydromet-image-slot"'))
        editable_formats = (
            'data-hydromet-format="pronostico-diario"',
            'data-hydromet-format="pronostico-semanal"',
            'data-hydromet-format="indice-ultravioleta"',
        )
        self.assertTrue(all(value in self.document for value in editable_formats))
        first_editable = self.document.index(editable_formats[0])
        self.assertNotIn("hydromet-image-slot", self.document[:first_editable])

    def test_editable_area_supports_file_drop_paste_selection_and_crop(self) -> None:
        self.assertIn('type="file" accept="image/*"', self.document)
        self.assertIn('addEventListener("drop"', self.feature)
        self.assertIn('addEventListener("paste"', self.feature)
        self.assertIn('addEventListener("contextmenu"', self.feature)
        self.assertIn("function startCrop", self.feature)
        self.assertIn("function applyCrop", self.feature)
        self.assertIn("top: 21%", self.styles)
        self.assertIn("left: 5%", self.styles)
        self.assertIn("width: 90%", self.styles)
        self.assertIn("height: 51.5%", self.styles)
        self.assertIn("contain: layout paint", self.styles)
        self.assertIn("clip-path: inset(0)", self.styles)
        self.assertIn("inset: 0", self.styles)
        self.assertNotIn("inset: 2.5%", self.styles)

    def test_uv_risk_is_detected_from_the_inserted_chart(self) -> None:
        self.assertEqual(1, self.document.count('class="hydromet-uv-risk"'))
        self.assertIn("function classifyUvRisk", self.feature)
        self.assertIn("function updateUvRisk", self.feature)
        for risk in ("Extremo", "Muy Alto", "Alto", "Moderado", "Bajo"):
            self.assertIn(f'label: "{risk}"', self.feature)
        self.assertIn(".hydromet-uv-risk", self.styles)
        self.assertIn(
            '[data-hydromet-format="indice-ultravioleta"] .hydromet-image-slot',
            self.styles,
        )
        self.assertIn("top: 24.5%", self.styles)
        self.assertIn("left: 2.5%", self.styles)
        self.assertIn("width: 95%", self.styles)
        self.assertIn("height: 50%", self.styles)
        for report_format in ("pronostico-diario", "pronostico-semanal"):
            self.assertIn(
                f'[data-hydromet-format="{report_format}"] .hydromet-image-slot',
                self.styles,
            )
        self.assertIn("top: 19.5%", self.styles)
        self.assertIn("height: 54%", self.styles)

    def test_one_datetime_control_updates_every_report_page(self) -> None:
        self.assertEqual(1, self.document.count('id="hydromet-datetime-trigger"'))
        self.assertEqual(6, self.document.count('class="hydromet-page-datetime"'))
        self.assertEqual(6, self.document.count('class="hydromet-page-date"'))
        self.assertEqual(6, self.document.count('class="hydromet-page-time"'))
        self.assertIn("function initializeDateTimeControl", self.feature)
        self.assertIn("function updatePageDateTimes", self.feature)
        self.assertIn("formatPageDate", self.feature)
        self.assertIn("formatPageTime", self.feature)
        self.assertIn(".hydromet-date-picker", self.styles)
        graphics_panel = self.document.index('data-hydromet-report-panel="graphics"')
        datetime_trigger = self.document.index('id="hydromet-datetime-trigger"')
        design_panel = self.document.index('data-hydromet-report-panel="design"')
        self.assertLess(graphics_panel, datetime_trigger)
        self.assertLess(datetime_trigger, design_panel)
        self.assertIn('if (tabName !== "graphics") {', self.feature)
        self.assertIn("closeDatePicker();", self.feature)

    def test_graphics_and_design_are_independent_tabs(self) -> None:
        self.assertEqual(2, self.document.count('data-hydromet-report-tab='))
        self.assertIn('data-hydromet-report-tab="graphics"', self.document)
        self.assertIn('data-hydromet-report-tab="design"', self.document)
        self.assertIn('data-hydromet-report-panel="graphics"', self.document)
        self.assertIn('data-hydromet-report-panel="design"', self.document)
        design_panel = self.document.index('data-hydromet-report-panel="design"')
        report_stack = self.document.index('class="hydromet-report-stack"')
        self.assertLess(design_panel, report_stack)
        self.assertIn("function initializeReportTabs", self.feature)
        self.assertIn('selectReportTab("design")', self.feature)
        self.assertEqual(1, self.feature.count('selectReportTab("design")'))

    def test_graphics_tab_has_compact_editable_data_tables(self) -> None:
        graphics_start = self.document.index('data-hydromet-report-panel="graphics"')
        design_start = self.document.index('data-hydromet-report-panel="design"')
        graphics = self.document[graphics_start:design_start]
        self.assertIn('data-hydromet-data-table="flows"', graphics)
        self.assertIn('data-hydromet-data-table="temperatures"', graphics)
        self.assertIn(">Caudales</span>", graphics)
        self.assertIn(">Temperaturas</span>", graphics)
        self.assertIn(">Estación Caudales</th>", graphics)
        self.assertIn("Temperatura (°C)</th>", graphics)
        self.assertGreaterEqual(graphics.count(">Valor</th>"), 1)
        for station in ("Tomebamba", "Yanuncay", "Tarqui", "Machángara"):
            self.assertIn(f">{station}</td>", graphics)
        for station in (
            "MET_TixánPTAP",
            "MET_SayausiPTAP",
            "MET_CebollarPTAP",
            "MET_ElValle",
            "MET_UcubambaPTAR",
        ):
            self.assertIn(f">{station}</td>", graphics)
        self.assertEqual(30, graphics.count('contenteditable="true"'))
        self.assertNotIn("Agregar fila", graphics)
        self.assertEqual(3, graphics.count('class="hydromet-data-trigger"'))
        self.assertEqual(1, graphics.count("hydromet-data-table-wrap hydromet-data-panel"))
        self.assertEqual(2, graphics.count("hydromet-data-panel hydromet-rain-dashboard"))
        self.assertEqual(2, graphics.count('class="hydromet-run-button"'))
        self.assertIn('data-hydromet-run="rainfall"', graphics)
        self.assertIn('data-hydromet-run="temperatures"', graphics)
        self.assertIn(".hydromet-data-accordion", self.styles)
        self.assertIn(".hydromet-data-trigger", self.styles)
        self.assertIn(".hydromet-data-panel[hidden]", self.styles)
        self.assertIn(".hydromet-data-table tbody tr:hover td", self.styles)
        self.assertIn(".hydromet-run-button", self.styles)
        self.assertIn(".hydromet-rain-dashboard-grid", self.styles)
        self.assertIn("hydromet-rain-table-scroll", graphics)
        self.assertIn(".hydromet-rain-table-scroll", self.styles)
        self.assertIn("scrollbar-gutter: stable", self.styles)
        self.assertIn("min-height: 100%", self.styles)
        self.assertIn("box-shadow: none", self.styles)
        self.assertIn("margin: 18px auto 26px", self.styles)
        self.assertIn("min-width: 0 !important", self.styles)
        self.assertIn("function initializeGraphicsTables", self.feature)
        self.assertIn('trigger.setAttribute("aria-expanded", String(shouldOpen))', self.feature)
        self.assertIn('CustomEvent("agender:hydromet-run"', self.feature)

    def test_rainfall_table_has_an_independent_date_seeded_from_report_date(self) -> None:
        graphics_start = self.document.index('data-hydromet-report-panel="graphics"')
        design_start = self.document.index('data-hydromet-report-panel="design"')
        graphics = self.document[graphics_start:design_start]
        self.assertIn('data-hydromet-data-table="rainfall"', graphics)
        self.assertIn(">Lluvias</span>", graphics)
        self.assertIn('placeholder="AAAA-MM-DD"', graphics)
        self.assertIn("function parseCalendarDay", self.feature)
        for station in (
            "MataderoSayausi", "Sayausi", "Cebollar", "Totoracocha",
            "SoldadosPTAR", "YanuncayPucan", "Labrado", "Saucay", "Tixán",
            "Chanlud", "Narancay", "Huizhil", "Ricaurte", "Ucubamba",
            "Challuabamba", "ElValle", "Llaviucu", "Chirimachay",
            "Toreadora", "Portete", "Irquis",
        ):
            self.assertIn(f"<td>{station}</td>", graphics)
        self.assertIn("let rainReportDate = null", self.feature)
        self.assertIn("let rainDateWasChanged = false", self.feature)
        self.assertIn("formatCalendarDay(rainReportDate || reportDate)", self.feature)
        self.assertEqual(21, graphics.count('inputmode="decimal"') - 9)
        self.assertEqual(20, graphics.count(">0</td>"))
        self.assertIn('inputmode="decimal">0.00</td>', graphics)
        self.assertIn('data-hydromet-clear="rainfall"', graphics)
        self.assertIn(">Configurar</span>", graphics)
        self.assertIn(">Limpiar</span>", graphics)
        self.assertIn("function clearRainObservations", self.feature)
        self.assertIn("function updateRainSummary", self.feature)
        self.assertIn("data-hydromet-rain-start-time", graphics)
        self.assertIn("data-hydromet-rain-end-time", graphics)
        self.assertIn("data-hydromet-rain-filled", graphics)
        self.assertIn("data-hydromet-rain-average", graphics)
        self.assertIn("data-hydromet-rain-preview-output", graphics)
        self.assertNotIn("data-hydromet-rain-search", graphics)
        self.assertIn("background: #fff", self.styles)
        self.assertIn("color: #1b1b1b", self.styles)

    def test_rainfall_execution_generates_and_places_the_map_in_design(self) -> None:
        main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        generator = (ROOT / "backend/hydromet_rain_map.py").read_text(encoding="utf-8")

        self.assertIn('data-hydromet-run="rainfall"', self.document)
        self.assertIn("data-hydromet-rain-map-slot", self.document)
        self.assertIn("data-hydromet-rain-map-output", self.document)
        self.assertIn("function readRainObservations", self.feature)
        self.assertIn("async function runRainMapGeneration", self.feature)
        self.assertIn('fetch("/api/reports/hydromet-network/rain-map"', self.feature)
        self.assertIn("function pollRainMap", self.feature)
        self.assertIn("function placeGeneratedRainMap", self.feature)
        self.assertIn("function placeRainMapPreview", self.feature)
        self.assertIn("job.previewUrl", self.feature)
        self.assertIn(".hydromet-generated-map-slot", self.styles)
        self.assertIn("object-fit: contain", self.styles)
        self.assertIn("left: 3.5%", self.styles)
        self.assertIn("width: 93%", self.styles)
        self.assertIn("height: 58.5%", self.styles)
        self.assertIn(
            '[data-hydromet-format="lluvias"] .hydromet-generated-map-slot',
            self.styles,
        )
        self.assertIn("top: 19.5%", self.styles)
        self.assertIn("left: 2.5%", self.styles)
        self.assertIn("width: 95%", self.styles)
        self.assertIn("height: 57.5%", self.styles)
        self.assertIn(
            '[data-hydromet-format="temperaturas"] .hydromet-generated-map-slot',
            self.styles,
        )
        self.assertIn('@app.post("/api/reports/hydromet-network/rain-map"', main)
        self.assertIn('@app.get("/api/reports/hydromet-network/rain-map/{job_id}/preview")', main)
        self.assertIn("background_tasks.add_task(execute_rain_map_job, job_id)", main)
        self.assertIn("def generate_rain_map(", generator)
        self.assertIn('"BD_Obs.xlsx"', generator)
        self.assertIn('f"mapa_{report_date.isoformat()}.svg"', generator)

    def test_rainfall_parameters_are_editable_and_control_generation(self) -> None:
        main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        generator = (ROOT / "backend/hydromet_rain_map.py").read_text(encoding="utf-8")

        self.assertIn('data-hydromet-params-trigger="rainfall"', self.document)
        self.assertIn('data-hydromet-params="rainfall"', self.document)
        expected_inputs = (
            ('search_radius', 'value="10"'),
            ('p', 'value="2"'),
            ('grid_resolution', 'value="0.1"'),
            ('n_round', 'value="2"'),
            ('plot_logo', 'type="checkbox" checked'),
            ('plot_design', 'type="checkbox" checked'),
        )
        for name, default_markup in expected_inputs:
            self.assertIn(f'name="{name}"', self.document)
            self.assertIn(default_markup, self.document)
        self.assertIn("function readRainMapParameters", self.feature)
        self.assertIn("function resetRainMapParameters", self.feature)
        self.assertIn("parameters,", self.feature)
        self.assertIn("class HydrometRainMapParameters", main)
        self.assertIn('"search_radius": payload.parameters.searchRadius', main)
        self.assertIn('"grid_resolution": payload.parameters.gridResolution', main)
        self.assertIn('"plot_design": payload.parameters.plotDesign', main)
        self.assertIn("grid_size = _grid_size(bounds, grid_resolution)", generator)
        self.assertIn("search_radius=search_radius", generator)
        self.assertIn("p=p", generator)
        self.assertIn("n_round=n_round", generator)
        self.assertIn("if plot_design:", generator)
        self.assertIn("_compose_map_design_svg(", generator)
        self.assertIn("if plot_logo:", generator)
        self.assertIn(".hydromet-params-popover", self.styles)

    def test_temperature_execution_generates_and_places_the_map_in_design(self) -> None:
        main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        generator = (ROOT / "backend/hydromet_temperature_map.py").read_text(encoding="utf-8")

        self.assertIn('data-hydromet-run="temperatures"', self.document)
        self.assertIn("data-hydromet-temperature-map-slot", self.document)
        self.assertIn("data-hydromet-temperature-map-output", self.document)
        self.assertIn("function readTemperatureObservations", self.feature)
        self.assertIn("async function runTemperatureMapGeneration", self.feature)
        self.assertIn('fetch("/api/reports/hydromet-network/temperature-map"', self.feature)
        self.assertIn("function pollTemperatureMap", self.feature)
        self.assertIn("function placeGeneratedTemperatureMap", self.feature)
        self.assertIn('@app.post("/api/reports/hydromet-network/temperature-map"', main)
        self.assertIn("background_tasks.add_task(execute_temperature_map_job, job_id)", main)
        self.assertIn("def generate_temperature_map(", generator)
        self.assertIn("COOL_STOPS", generator)
        self.assertIn("WARM_STOPS", generator)
        self.assertIn('placeholder="AAAA-MM-DD HH:mm"', self.document)
        self.assertIn("function parseCalendarDateTime", self.feature)
        self.assertIn("dateInterpolation:", self.feature)
        self.assertIn("dateInterpolation: datetime", main)
        self.assertIn(
            "fetch_ierse_temperature_observations(date_interpolation)",
            generator,
        )
        self.assertNotIn(
            "fetch_ierse_temperature_observations(report_date, end_time)",
            generator,
        )

    def test_design_export_selects_pages_and_saves_native_quality_jpegs(self) -> None:
        main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        exporter = (ROOT / "backend/hydromet_report_export.py").read_text(encoding="utf-8")

        self.assertIn('id="hydromet-design-export-open"', self.document)
        self.assertIn('id="hydromet-design-export-dialog"', self.document)
        self.assertIn('id="hydromet-design-export-all"', self.document)
        for report_format in (
            "caudales",
            "lluvias",
            "temperaturas",
            "pronostico-diario",
            "pronostico-semanal",
            "indice-ultravioleta",
        ):
            self.assertIn(f'value="{report_format}" checked', self.document)
            self.assertIn(f'"{report_format}"', self.export_feature)
        self.assertIn("function serializeDesignForExport", self.export_feature)
        self.assertIn("new URL(source, document.baseURI).href", self.export_feature)
        self.assertIn(
            'image.classList.contains("hydromet-report-template")',
            self.export_feature,
        )
        self.assertIn('clonedImage.removeAttribute("src")', self.export_feature)
        self.assertIn("NotasHydrometDesignExport", self.export_feature)
        self.assertIn('fetch("/api/reports/hydromet-network/export-designs"', self.export_feature)
        self.assertIn("reportTime:", self.export_feature)
        self.assertIn(".hydromet-design-export-dialog", self.styles)
        self.assertIn('@app.post("/api/reports/hydromet-network/export-designs")', main)
        self.assertIn("EXPORT_SIZE = 4167", exporter)
        self.assertIn("quality=100", exporter)
        self.assertIn("subsampling=0", exporter)
        self.assertIn('dpi=(300, 300)', exporter)
        self.assertIn('f"{report_key}_{report_date.isoformat()}.jpg"', exporter)
        self.assertIn('f"{report_date.isoformat()}_{report_time.replace(\':\', \'\')}"', exporter)

    def test_flow_values_feed_the_matching_report_rows(self) -> None:
        for river in ("tomebamba", "yanuncay", "tarqui", "machangara"):
            self.assertIn(f'data-flow-input="{river}"', self.document)
            self.assertIn(f'data-flow-output="{river}"', self.document)
        self.assertEqual(4, self.document.count('class="hydromet-flow-report-row"'))
        self.assertIn("function syncFlowReportValue", self.feature)
        self.assertIn('table?.addEventListener("input"', self.feature)
        self.assertIn(".hydromet-flow-report-data", self.styles)
        self.assertIn(".hydromet-flow-report-row", self.styles)
        self.assertNotIn(".hydromet-flow-state::after", self.styles)

    def test_flow_thresholds_set_normal_prealert_and_alert_styles(self) -> None:
        expected_thresholds = (
            "tomebamba: { normalMaximum: 29, alertMinimum: 50 }",
            "yanuncay: { normalMaximum: 32, alertMinimum: 50 }",
            "tarqui: { normalMaximum: 15, alertMinimum: 30 }",
            "machangara: { normalMaximum: 19, alertMinimum: 50 }",
        )
        for threshold in expected_thresholds:
            self.assertIn(threshold, self.feature)
        self.assertIn('status = "normal"', self.feature)
        self.assertIn('status = "prealert"', self.feature)
        self.assertIn('status = "alert"', self.feature)
        self.assertIn(".is-normal", self.styles)
        self.assertIn(".is-prealert", self.styles)
        self.assertIn(".is-alert", self.styles)
        self.assertIn("background: #ffb800", self.styles)
        self.assertIn("font-size: 1.12em", self.styles)
        self.assertIn('font-family: "Azo Sans"', self.styles)
        self.assertIn("font-size: 3.1cqw", self.styles)
        self.assertIn("top: 33.1%", self.styles)
        self.assertIn("left: 32.9%", self.styles)
        self.assertIn("width: 40%", self.styles)

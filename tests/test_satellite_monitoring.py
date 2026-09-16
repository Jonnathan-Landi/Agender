from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]


class SatelliteMonitoringNavigationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        cls.login = (ROOT / "frontend/js/core/login.js").read_text(encoding="utf-8")
        cls.app = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
        cls.feature = (ROOT / "frontend/js/features/radar-caxx.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "frontend/css/radar-caxx.css").read_text(encoding="utf-8")
        cls.geodata = (ROOT / "frontend/js/data/radar-caxx-geodata.js").read_text(encoding="utf-8")
        cls.tauri_config = (ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8")
        cls.backend = (ROOT / "backend/main.py").read_text(encoding="utf-8")

    def test_satellite_monitoring_is_below_climate(self) -> None:
        climate = self.document.index('data-nav-group="climate"')
        satellite = self.document.index('data-nav-group="satellite-monitoring"')

        self.assertLess(climate, satellite)
        self.assertIn('<span class="nav-label">Monitoreo Satelital</span>', self.document)

    def test_radar_caxx_opens_its_own_view(self) -> None:
        self.assertIn('data-view="radar-caxx"', self.document)
        self.assertIn('id="radar-caxx-view"', self.document)
        self.assertIn('id="radar-caxx-title">Radar Caxx</h1>', self.document)

    def test_satellite_views_use_independent_permissions(self) -> None:
        self.assertIn('"radar-caxx": "radar-caxx"', self.login)
        self.assertIn('goes19: "goes19"', self.login)
        self.assertIn('if (modules.has("radar-caxx")) window.NotasRadarCaxx?.init();', self.app)
        self.assertIn('if (modules.has("goes19")) window.NotasGoes19?.init();', self.app)
        self.assertNotIn('if (modules.has("climatology")) window.NotasRadarCaxx?.init();', self.app)
        self.assertNotIn('if (modules.has("climatology")) window.NotasGoes19?.init();', self.app)

    def test_license_generator_exposes_satellite_modules(self) -> None:
        controller = (ROOT / "frontend/js/core/license-admin.js").read_text(encoding="utf-8")
        self.assertIn('id="license-satellite-all"', self.document)
        self.assertIn('value="radar-caxx"', self.document)
        self.assertIn('value="goes19"', self.document)
        self.assertIn("setupPermissionGroup(satelliteAll, satelliteModules)", controller)

    def test_radar_map_uses_utm_data_and_metric_coverage_rings(self) -> None:
        self.assertIn('"crs":"EPSG:32717"', self.geodata)
        self.assertIn('"radar":[694951.002,9694792.553]', self.geodata)
        self.assertIn('"radii":[20000,60000,100000]', self.geodata)
        self.assertIn("data.radii", self.feature)
        self.assertIn('loadScriptOnce("js/data/radar-caxx-geodata.js")', self.app)
        self.assertIn("const viewportAspect", self.feature)
        self.assertIn("const minX = radarX - width / 2", self.feature)
        self.assertIn("new ResizeObserver", self.feature)
        self.assertIn("radarY - 135_000", self.feature)
        self.assertIn("radarY + 105_000", self.feature)

    def test_weather_radar_marker_is_compact(self) -> None:
        self.assertIn("const markerSize = 9_000", self.feature)
        self.assertIn("r: 1_250", self.feature)

    def test_map_uses_the_entire_available_view(self) -> None:
        self.assertNotIn("radar-caxx-coordinate-card", self.document)
        self.assertNotIn("radar-caxx-info", self.document)
        self.assertNotIn("Cobertura territorial del radar", self.document)
        self.assertIn("height: calc(100vh - 16px)", self.styles)
        self.assertIn("margin: -20px -24px", self.styles)
        self.assertIn("flex: 1 1 auto", self.styles)

    def test_cuenca_uses_the_goeshub_double_outline_label_style(self) -> None:
        self.assertIn("radar-cuenca-halo", self.feature)
        self.assertIn("radar-cuenca-label-halo", self.feature)
        self.assertIn(".radar-cuenca-halo", self.styles)
        self.assertIn("stroke: #fff", self.styles)
        self.assertIn("font: 800 6500px", self.styles)
        self.assertIn(".radar-cuenca { fill: none", self.styles)

    def test_map_uses_an_utm_aligned_basemap_without_polygon_fills(self) -> None:
        self.assertIn("/api/radar-caxx/imagery/", self.feature)
        self.assertIn("function addImageryTiles", self.feature)
        self.assertIn("function addImageryExport", self.feature)
        self.assertIn("function imageryExportUrl", self.feature)
        self.assertIn('cache: "force-cache"', self.feature)
        self.assertIn("/api/radar-caxx/basemap.jpg?area=", self.feature)
        self.assertIn('retry.searchParams.set("retry"', self.feature)
        self.assertIn('image.classList.add("is-ready")', self.feature)
        self.assertLess(
            self.feature.index('image.addEventListener("load"'),
            self.feature.index('image.setAttribute("href", imageryExportUrl())'),
        )
        self.assertIn('class: "radar-country"', self.feature)
        self.assertNotIn("data.cantons.forEach", self.feature)
        self.assertNotIn(".radar-canton", self.styles)
        self.assertIn(".radar-country { fill: none; stroke: #fff", self.styles)
        self.assertIn("img-src 'self' data: blob:;", self.tauri_config)

    def test_weather_radar_svg_is_packaged(self) -> None:
        radar_icon = ROOT / "frontend/assets/radar-weather.svg"
        self.assertTrue(radar_icon.is_file())
        self.assertIn("Radar meteorológico", radar_icon.read_text(encoding="utf-8"))

    def test_coverage_rings_remain_visible_over_satellite_imagery(self) -> None:
        self.assertIn(".radar-radius { fill: none; stroke-width: 3", self.styles)
        self.assertIn("#ffe600", self.styles)
        self.assertIn("#00eaff", self.styles)
        self.assertIn("#ff3f7f", self.styles)
        self.assertIn("drop-shadow", self.styles)

    def test_goeshub_style_legend_is_inside_the_map(self) -> None:
        map_start = self.document.index('class="radar-caxx-map"')
        legend = self.document.index('class="radar-map-legend"')
        map_end = self.document.index('</div>', legend)
        self.assertLess(map_start, legend)
        self.assertLess(legend, map_end)
        self.assertIn('src="assets/radar-weather.svg"', self.document[legend:])
        self.assertIn("backdrop-filter: blur(14px)", self.styles)

    def test_radar_animation_controls_and_backend_routes_are_connected(self) -> None:
        for control in ("radar-caxx-previous", "radar-caxx-play", "radar-caxx-next"):
            self.assertIn(f'id="{control}"', self.document)
        self.assertIn('fetch("/api/radar-caxx/frames"', self.feature)
        self.assertIn("radar-data-overlay", self.feature)
        self.assertIn("window.setInterval(() => showFrame", self.feature)
        self.assertIn('@app.get("/api/radar-caxx/frames")', self.backend)
        self.assertIn('@app.get("/api/radar-caxx/frames/{frame_id}.png")', self.backend)
        self.assertIn('@app.get("/api/radar-caxx/basemap.jpg")', self.backend)

    def test_control_center_limits_recent_frames_and_preloads_the_basemap(self) -> None:
        self.assertIn('id="radar-caxx-area"', self.document)
        self.assertIn('id="radar-caxx-frame-count"', self.document)
        self.assertIn('<option value="25">25 (2 horas)</option>', self.document)
        self.assertIn('<option value="49">49 (4 horas)</option>', self.document)
        self.assertIn("availableFrames.slice(-limit)", self.feature)
        self.assertIn("Math.min(49", self.feature)
        self.assertIn("__radarCaxxBasemapPreload", self.app)
        self.assertIn("RADAR_BASEMAP_BOUNDS", self.backend)

    def test_area_selector_switches_packaged_surveillance_shapes(self) -> None:
        self.assertIn('"subcuencas":', (ROOT / "scripts/generate-radar-geodata.py").read_text(encoding="utf-8"))
        self.assertIn('"zonaUrbana":', (ROOT / "scripts/generate-radar-geodata.py").read_text(encoding="utf-8"))
        self.assertIn("data.subcuencas.forEach", self.feature)
        self.assertIn("data.zonaUrbana.forEach", self.feature)
        self.assertIn("showSelectedArea", self.feature)
        self.assertIn("?area=${encodeURIComponent(areaSelect.value)}", self.feature)
        self.assertNotIn("moveCamera", self.feature)
        self.assertNotIn("clip-path", self.feature)
        self.assertIn("surveillanceFrame", self.feature)
        self.assertIn('svg.setAttribute("viewBox", surveillanceFrames[selection]', self.feature)

    def test_mp4_export_uses_selected_area_and_visible_frame_limit(self) -> None:
        self.assertIn('id="radar-caxx-export"', self.document)
        self.assertIn('id="radar-caxx-export-status"', self.document)
        self.assertIn("Exportado en:", self.feature)
        self.assertIn("Elige la carpeta y el nombre", self.feature)
        self.assertIn('fetch("/api/radar-caxx/export-mp4"', self.feature)
        self.assertIn("frameIds: frames.map((frame) => frame.id)", self.feature)
        self.assertNotIn("canvas.toDataURL", self.feature)
        self.assertNotIn("renderVideoFrame", self.feature)
        self.assertIn('@app.post("/api/radar-caxx/export-mp4")', self.backend)

    def test_packaged_shapes_no_longer_depend_on_temporary_folder(self) -> None:
        generator = (ROOT / "scripts/generate-radar-geodata.py").read_text(encoding="utf-8")
        package_spec = (ROOT / "packaging/agender-backend.spec").read_text(encoding="utf-8")
        self.assertNotIn('ROOT / "shape_Temporales"', generator)
        for filename in ("Cantones_Ecuador.gpkg", "ecuador.gpkg", "Subcuencas.gpkg", "ZonaUrbana.gpkg"):
            self.assertTrue((ROOT / "backend/data/radar_caxx" / filename).is_file())
        self.assertIn('"backend" / "data" / "radar_caxx"', package_spec)
        self.assertTrue((ROOT / "backend/data/radar_caxx/Subcuencas.gpkg").is_file())
        self.assertTrue((ROOT / "backend/data/radar_caxx/ZonaUrbana.gpkg").is_file())

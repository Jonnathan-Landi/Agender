from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from backend import hydromet_report_export


class HydrometReportExportTests(unittest.TestCase):
    def test_capture_document_uses_native_size_and_sanitizes_active_content(self) -> None:
        document = hydromet_report_export._build_capture_document(
            '<figure class="hydromet-report-page" onclick="bad()">'
            '<script>bad()</script><img src="data:image/png;base64,AA=="></figure>',
            ".hydromet-report-page { position: relative; }",
        )

        self.assertIn("4167px", document)
        self.assertNotIn("<base", document)
        self.assertNotIn("<script", document.lower())
        self.assertNotIn("onclick", document.lower())

    def test_capture_document_removes_the_base_from_the_browser_layer(self) -> None:
        document = hydromet_report_export._build_capture_document(
            '<figure class="hydromet-report-page">'
            '<img class="hydromet-report-template" '
            'src="http://unavailable/assets/hydromet-report/04-pronostico-diario.jpeg">'
            "</figure>",
            ".hydromet-report-page { position: relative; }",
            "pronostico-diario",
        )

        self.assertNotIn("hydromet-report-template", document)
        self.assertNotIn("http://unavailable", document)
        self.assertIn("background: transparent !important", document)

    def test_export_creates_a_dated_folder_and_one_jpeg_per_selection(self) -> None:
        reports = [
            {
                "format": "caudales",
                "html": '<figure class="hydromet-report-page">'
                '<img class="hydromet-report-template" src="01-caudales.jpeg">'
                "</figure>",
            },
            {
                "format": "lluvias",
                "html": '<figure class="hydromet-report-page">'
                '<img class="hydromet-report-template" src="02-lluvias.jpeg">'
                "</figure>",
            },
        ]

        def fake_capture(_page, _html: Path, png: Path) -> None:
            Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(png, format="PNG")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "2026-07-23_0800").mkdir()
            browser = MagicMock()
            browser.new_page.return_value = object()
            with (
                patch.object(hydromet_report_export, "choose_directory", return_value=root),
                patch.object(
                    hydromet_report_export,
                    "chromium_browser",
                    return_value=nullcontext(browser),
                ),
                patch.object(hydromet_report_export, "_capture_page", side_effect=fake_capture),
            ):
                result = hydromet_report_export.export_hydromet_designs(
                    reports,
                    date(2026, 7, 23),
                    "08:00",
                )

            output = root / "2026-07-23_0800_02"
            self.assertTrue(result["ok"])
            self.assertEqual(output, Path(result["folder"]))
            self.assertEqual(2, result["count"])
            self.assertEqual(
                ["caudales_2026-07-23.jpg", "lluvias_2026-07-23.jpg"],
                result["files"],
            )
            for filename in result["files"]:
                with Image.open(output / filename) as image:
                    self.assertEqual("JPEG", image.format)
                    self.assertEqual(
                        (hydromet_report_export.EXPORT_SIZE,) * 2,
                        image.size,
                    )
                    self.assertEqual((300, 300), tuple(round(value) for value in image.info["dpi"]))

    def test_jpeg_composition_places_transparent_overlay_on_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.png"
            overlay = root / "overlay.png"
            output = root / "output.jpg"
            Image.new("RGB", (24, 24), "#ff8300").save(template)
            layer = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
            for x in range(8, 16):
                for y in range(8, 16):
                    layer.putpixel((x, y), (20, 180, 40, 255))
            layer.save(overlay)

            with patch.object(hydromet_report_export, "EXPORT_SIZE", 24):
                hydromet_report_export._save_maximum_quality_jpeg(
                    overlay,
                    output,
                    template,
                )

            with Image.open(output) as result:
                self.assertGreater(result.getpixel((2, 2))[0], 220)
                center = result.getpixel((12, 12))
                self.assertGreater(center[1], center[0] * 2)

    def test_canceled_folder_selection_does_not_create_output(self) -> None:
        reports = [
            {"format": "temperaturas", "html": '<figure class="hydromet-report-page"></figure>'},
        ]
        with patch.object(hydromet_report_export, "choose_directory", return_value=None):
            result = hydromet_report_export.export_hydromet_designs(
                reports,
                date(2026, 7, 23),
                "08:00",
            )

        self.assertTrue(result["canceled"])

    def test_unknown_or_duplicate_designs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no reconocido"):
            hydromet_report_export._validate_reports(
                [{"format": "otro", "html": "<figure></figure>"}]
            )
        with self.assertRaisesRegex(ValueError, "más de una vez"):
            hydromet_report_export._validate_reports(
                [
                    {"format": "caudales", "html": "<figure></figure>"},
                    {"format": "caudales", "html": "<figure></figure>"},
                ]
            )

    def test_integrated_renderer_timeout_is_reported_as_an_export_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html_path = root / "report.html"
            html_path.write_text("<html></html>", encoding="utf-8")
            page = MagicMock()
            page.goto.side_effect = PlaywrightTimeoutError("timeout")
            with self.assertRaisesRegex(ValueError, "tardó demasiado"):
                hydromet_report_export._capture_page(
                    page,
                    html_path,
                    root / "report.png",
                )

    def test_design_export_has_no_external_browser_dependency(self) -> None:
        source = Path(hydromet_report_export.__file__).read_text(encoding="utf-8")
        self.assertIn("with chromium_browser() as browser", source)
        self.assertNotIn("subprocess", source)


if __name__ == "__main__":
    unittest.main()

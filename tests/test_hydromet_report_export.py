from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend import hydromet_report_export


class HydrometReportExportTests(unittest.TestCase):
    def test_capture_document_uses_native_size_and_sanitizes_active_content(self) -> None:
        document = hydromet_report_export._build_capture_document(
            '<figure class="hydromet-report-page" onclick="bad()">'
            '<script>bad()</script><img src="data:image/png;base64,AA=="></figure>',
            ".hydromet-report-page { position: relative; }",
            "http://127.0.0.1:4567/",
        )

        self.assertIn("4167px", document)
        self.assertIn('<base href="http://127.0.0.1:4567/">', document)
        self.assertNotIn("<script", document.lower())
        self.assertNotIn("onclick", document.lower())

    def test_export_creates_a_dated_folder_and_one_jpeg_per_selection(self) -> None:
        reports = [
            {"format": "caudales", "html": '<figure class="hydromet-report-page"></figure>'},
            {"format": "lluvias", "html": '<figure class="hydromet-report-page"></figure>'},
        ]

        def fake_capture(_edge: Path, _html: Path, png: Path, _profile: Path) -> None:
            Image.new("RGB", (40, 40), "#ff8300").save(png, format="PNG")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "2026-07-23_0800").mkdir()
            with (
                patch.object(hydromet_report_export, "choose_directory", return_value=root),
                patch.object(hydromet_report_export, "_find_edge", return_value=Path("edge.exe")),
                patch.object(hydromet_report_export, "_capture_page", side_effect=fake_capture),
            ):
                result = hydromet_report_export.export_hydromet_designs(
                    reports,
                    date(2026, 7, 23),
                    "08:00",
                    "http://127.0.0.1:4567/",
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
                    self.assertEqual((300, 300), tuple(round(value) for value in image.info["dpi"]))

    def test_canceled_folder_selection_does_not_create_output(self) -> None:
        reports = [
            {"format": "temperaturas", "html": '<figure class="hydromet-report-page"></figure>'},
        ]
        with (
            patch.object(hydromet_report_export, "choose_directory", return_value=None),
            patch.object(hydromet_report_export, "_find_edge", return_value=Path("edge.exe")),
        ):
            result = hydromet_report_export.export_hydromet_designs(
                reports,
                date(2026, 7, 23),
                "08:00",
                "http://127.0.0.1:4567/",
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


if __name__ == "__main__":
    unittest.main()

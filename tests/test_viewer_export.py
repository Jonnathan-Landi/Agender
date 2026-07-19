import csv
import io
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from openpyxl import load_workbook
from fastapi import HTTPException

from backend.viewer.api import BatchExportRequest, ExportRequest, export_batch, export_data, ingest_file


class ViewerExportTests(TestCase):
    def _session(self, root: str):
        source = Path(root) / "EST001.csv"
        source.write_text(
            "fecha_hora,temperatura,precipitacion\n"
            "2026-01-01 00:00:00,20,1\n"
            "2026-01-01 00:30:00,22,2\n"
            "2026-01-01 01:00:00,24,3\n"
            "2026-01-02 00:00:00,26,4\n",
            encoding="utf-8",
        )
        return ingest_file(source, source.name)

    def test_original_export_supports_dat_csv_and_excel(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = self._session(root)
            base = {
                "session_id": session.session_id,
                "station_code": "EST001",
                "variables": ["temperatura"],
                "resolution": "original",
            }

            dat_response = export_data(ExportRequest(**base, file_format="dat"))
            csv_response = export_data(ExportRequest(**base, file_format="csv"))
            excel_response = export_data(ExportRequest(**base, file_format="xlsx"))

        self.assertIn(b"\t", dat_response.body)
        csv_rows = list(csv.reader(io.StringIO(csv_response.body.decode("utf-8-sig"))))
        self.assertEqual(["fecha_hora", "temperatura"], csv_rows[0])
        self.assertEqual(5, len(csv_rows))
        workbook = load_workbook(io.BytesIO(excel_response.body), read_only=True)
        self.assertEqual(("fecha_hora", "temperatura"), next(workbook.active.values))

    def test_daily_export_uses_variable_aggregation_and_date_filter(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = self._session(root)
            response = export_data(
                ExportRequest(
                    session_id=session.session_id,
                    station_code="EST001",
                    variables=["temperatura", "precipitacion"],
                    start_date="2026-01-01",
                    end_date="2026-01-01",
                    resolution="day",
                    min_coverage=1,
                    file_format="csv",
                )
            )

        rows = list(csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
        self.assertEqual(
            ["Fecha", "temperatura", "precipitacion"],
            rows[0],
        )
        self.assertEqual("22.0", rows[1][1])
        self.assertEqual("6.0", rows[1][2])
        self.assertEqual(2, len(rows))

    def test_session_exposes_bounds_and_rejects_dates_outside_them(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = self._session(root)
            self.assertEqual("2026-01-01", session.first_date)
            self.assertEqual("2026-01-02", session.last_date)
            with self.assertRaisesRegex(HTTPException, "fuera del rango"):
                export_data(
                    ExportRequest(
                        session_id=session.session_id,
                        station_code="EST001",
                        variables=["temperatura"],
                        start_date="2025-12-31",
                        end_date="2026-01-02",
                        resolution="day",
                        file_format="csv",
                    )
                )

    def test_custom_resolution_accepts_multiple_hours(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = self._session(root)
            response = export_data(
                ExportRequest(
                    session_id=session.session_id,
                    station_code="EST001",
                    variables=["precipitacion"],
                    start_date="2026-01-01",
                    end_date="2026-01-02",
                    resolution="custom",
                    custom_value=2,
                    custom_unit="hour",
                    min_coverage=1,
                    file_format="csv",
                )
            )

        rows = list(csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
        self.assertEqual(["TIMESTAMP", "precipitacion"], rows[0])
        self.assertEqual("6.0", rows[1][1])
        self.assertIn('filename="EST001-2-hour.csv"', response.headers["content-disposition"])

    def test_export_can_be_saved_to_a_user_selected_destination(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = self._session(root)
            destination = Path(root) / "seleccionado.csv"
            with patch("backend.viewer.api._save_export_dialog", return_value=destination):
                result = export_data(
                    ExportRequest(
                        session_id=session.session_id,
                        station_code="EST001",
                        variables=["temperatura"],
                        resolution="day",
                        min_coverage=1,
                        file_format="csv",
                        choose_destination=True,
                    )
                )
            self.assertTrue(result["saved"])
            self.assertEqual("seleccionado.csv", result["filename"])
            self.assertIn("Fecha,temperatura", destination.read_text(encoding="utf-8-sig"))

    def test_batch_export_creates_one_file_per_station_in_one_folder(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            cache = Path(root) / "cache"
            source = Path(root) / "source"
            output = Path(root) / "output"
            cache.mkdir()
            source.mkdir()
            output.mkdir()
            for code, value in (("EST001", 20), ("EST002", 25)):
                (source / f"{code}.csv").write_text(
                    "fecha_hora,temperatura\n"
                    f"2026-01-01 00:00:00,{value}\n"
                    f"2026-01-01 00:05:00,{value + 1}\n",
                    encoding="utf-8",
                )
            request = SimpleNamespace(cookies={"agender_session": "session"})
            settings = {"rawIncludeSubfolders": True}
            with (
                patch("backend.viewer.api.current_user", return_value={"username": "admin", "role": "admin"}),
                patch("backend.viewer.api.read_settings", return_value=settings),
                patch("backend.viewer.api.materialize_source", return_value=(str(source), {"mode": "local"})),
                patch("backend.viewer.api._choose_export_folder", return_value=output),
            ):
                result = export_batch(
                    BatchExportRequest(
                        station_codes=["EST001", "EST002"],
                        source="raw",
                        resolution="5min",
                        min_coverage=1,
                        file_format="csv",
                    ),
                    request,
                )

            self.assertEqual(2, result["saved"])
            self.assertEqual(0, result["failed"])
            self.assertEqual(2, len(list(output.glob("*.csv"))))

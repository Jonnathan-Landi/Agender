import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import polars as pl

from backend.viewer.api import ExportRequest, export_data, get_data, ingest_file, parquet_path


class DischargeCurveTests(TestCase):
    def _source(self, root: str) -> Path:
        source = Path(root) / "LIM_Yanuncay-AJ-Tarqui.csv"
        source.write_text(
            "fecha_hora,Level_Min,Level_Max,Level_Avg\n"
            "2026-01-01 00:00:00,21,22,21.5\n"
            "2026-01-01 00:05:00,22,23,22.5\n",
            encoding="utf-8",
        )
        return source

    def test_raw_session_exposes_virtual_flows_without_materializing_them(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = ingest_file(
                self._source(root),
                "LIM_Yanuncay-AJ-Tarqui.csv",
                station_code="LIM_Yanuncay-AJ-Tarqui",
                source="raw",
            )

            self.assertEqual(["Q_Min", "Q_Max", "Q_Avg"], session.variables[-3:])
            self.assertNotIn("Q_Avg", pl.read_parquet(parquet_path(session.session_id)).columns)
            preview = get_data(
                session_id=session.session_id,
                variable="Q_Avg",
                year=2026,
                month=1,
                day=1,
                resolution="5min",
                min_coverage=1,
            )
            response = export_data(
                ExportRequest(
                    session_id=session.session_id,
                    station_code="LIM_Yanuncay-AJ-Tarqui",
                    variables=["Q_Min", "Q_Max", "Q_Avg"],
                    resolution="original",
                    file_format="csv",
                )
            )

        self.assertAlmostEqual(0.00000145966 * 1.5**3.3435, preview["y"][0])
        rows = list(csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
        self.assertEqual(["fecha_hora", "Q_Min", "Q_Max", "Q_Avg"], rows[0])
        self.assertAlmostEqual(0.00000145966, float(rows[1][1]))

    def test_processed_session_only_exposes_average_flow(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = ingest_file(
                self._source(root),
                "LIM_Yanuncay-AJ-Tarqui.csv",
                station_code="LIM_Yanuncay-AJ-Tarqui",
                source="quality",
            )

        self.assertIn("Q_Avg", session.variables)
        self.assertNotIn("Q_Min", session.variables)
        self.assertNotIn("Q_Max", session.variables)

    def test_station_without_curve_keeps_original_variables(self) -> None:
        with TemporaryDirectory() as root, patch("backend.viewer.api.CACHE_ROOT", Path(root) / "cache"):
            (Path(root) / "cache").mkdir()
            session = ingest_file(self._source(root), "OTHER.csv", station_code="OTHER", source="raw")

        self.assertFalse(any(variable.startswith("Q_") for variable in session.variables))

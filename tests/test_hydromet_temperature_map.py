from __future__ import annotations

import io
import tempfile
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from backend import hydromet_temperature_map
from backend.hydromet_rain_map import _expand_bounds_to_aspect


class HydrometTemperatureMapTests(unittest.TestCase):
    def test_design_uses_hydroclima_style_plot_and_axis_spacing(self) -> None:
        self.assertEqual((170, 150, 2180, 1160), hydromet_temperature_map.TEMPERATURE_PLOT_BOX)
        self.assertEqual(
            [-79.05, -79.0, -78.95, -78.9],
            hydromet_temperature_map._temperature_axis_ticks(-79.07, -78.89, 0.05),
        )
        self.assertEqual(
            [-2.92, -2.9, -2.88, -2.86, -2.84],
            hydromet_temperature_map._temperature_axis_ticks(-2.93, -2.83, 0.02),
        )
        self.assertEqual(9, len(hydromet_temperature_map.COOL_STOPS))
        self.assertEqual(9, len(hydromet_temperature_map.WARM_STOPS))
        source = Path(hydromet_temperature_map.__file__).read_text(encoding="utf-8")
        self.assertIn("padding = 0.009", source)
        self.assertIn("panel_width = round((right - left) * 0.24)", source)
        self.assertIn("panel_height = round((bottom - top) * 0.48)", source)
        self.assertIn("(right-left) * 0.35", source)
        self.assertIn("label_lines = [part.upper() for part in name.split()]", source)

    def test_hydroclima_stations_are_available(self) -> None:
        self.assertEqual(15, len(hydromet_temperature_map.station_names()))
        self.assertEqual(
            (
                "MET_TixánPTAP",
                "MET_SayausiPTAP",
                "MET_CebollarPTAP",
                "MET_ElValle",
                "MET_UcubambaPTAR",
            ),
            hydromet_temperature_map.manual_station_names(),
        )
        self.assertTrue(hydromet_temperature_map.BUFFER_PATH.is_file())
        features = hydromet_temperature_map._load_temperature_buffer_features()
        self.assertEqual(15, len(features))
        self.assertEqual("Bellavista", features[0]["properties"]["name"])

    def test_generation_creates_temperature_map(self) -> None:
        observations = {
            "MET_TixánPTAP": 10.78,
            "MET_SayausiPTAP": 9.4,
            "MET_CebollarPTAP": 10.89,
            "MET_ElValle": 9.94,
            "MET_UcubambaPTAR": 10.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(hydromet_temperature_map, "REPORT_ROOT", root):
                image_path = hydromet_temperature_map.generate_temperature_map(
                    user_id=7,
                    job_id="temperature-test",
                    date_interpolation=datetime(2026, 7, 23, 8, 45),
                    start_time="00:00",
                    end_time="20:31",
                    observations=observations,
                    remote_observations={
                        "SCP03_Casa Pérez": 11.2,
                        "SCP09_Parque Industrial": 10.4,
                    },
                    fetch_basemap=False,
                    grid_resolution=1,
                )

            self.assertEqual(
                root / "7/jobs/temperature-test/out/temperatura_2026-07-23.svg",
                image_path,
            )
            svg = image_path.read_text(encoding="utf-8")
            root_element = ET.fromstring(svg)
            self.assertEqual("2200", root_element.attrib["width"])
            self.assertEqual("1332", root_element.attrib["height"])
            self.assertIn("data:image/png;base64,", svg)
            self.assertIn('id="temperature-scale"', svg)
            self.assertIn("Temperatura mínima en Cuenca:", svg)
            self.assertIn("<path", svg)

    def test_palette_switches_between_minimum_and_maximum_maps(self) -> None:
        self.assertEqual(
            hydromet_temperature_map.COOL_STOPS,
            hydromet_temperature_map._temperature_palette(max((9.4, 10.89))),
        )
        self.assertEqual(
            hydromet_temperature_map.WARM_STOPS,
            hydromet_temperature_map._temperature_palette(max((19.2, 24.5))),
        )

    def test_ierse_monthly_csv_is_filtered_by_selected_hour_and_aliases_station(self) -> None:
        content = (
            "timestamp;id_nombre;avgTC;maxTC;minTC\n"
            '"2026-07-23 19:00:00";"SCP03_Casa Pérez";15.1;16;14\n'
            '"2026-07-23 20:00:00";"SCP03_Casa Pérez";16.34;17;15\n'
            '"2026-07-23 20:00:00";"SCP17_Monumento a la Familia";15.8;16;15\n'
        ).encode()
        with patch(
            "backend.hydromet_temperature_map.urllib.request.urlopen",
            return_value=io.BytesIO(content),
        ):
            observations = hydromet_temperature_map.fetch_ierse_temperature_observations(
                datetime(2026, 7, 23, 20, 31),
            )

        self.assertEqual(
            {
                "SCP03_Casa Pérez": 16.34,
                "SCP17_Redondel Muñecas de Piedra": 15.8,
            },
            observations,
        )

    def test_ierse_hour_comes_from_interpolation_datetime_not_map_range(self) -> None:
        content = (
            "timestamp;id_nombre;avgTC;maxTC;minTC\n"
            '"2026-07-29 08:00:00";"SCP03_Casa Pérez";12.5;13;12\n'
            '"2026-07-29 20:00:00";"SCP03_Casa Pérez";18.5;19;18\n'
        ).encode()
        with patch(
            "backend.hydromet_temperature_map.urllib.request.urlopen",
            return_value=io.BytesIO(content),
        ) as urlopen:
            observations = hydromet_temperature_map.fetch_ierse_temperature_observations(
                datetime(2026, 7, 29, 8, 47),
            )

        self.assertEqual({"SCP03_Casa Pérez": 12.5}, observations)
        request = urlopen.call_args.args[0]
        request_payload = urllib.parse.parse_qs(request.data.decode("ascii"))
        self.assertEqual(["2026"], request_payload["year"])
        self.assertEqual(["07"], request_payload["month"])

    def test_background_job_preserves_interpolation_datetime(self) -> None:
        selected = datetime(2026, 7, 29, 8, 47)
        job_id = hydromet_temperature_map.create_temperature_map_job(
            user_id=7,
            date_interpolation=selected,
            start_time="00:00",
            end_time="20:00",
            observations={"MET_TixánPTAP": 12.5},
        )

        with patch.object(
            hydromet_temperature_map,
            "generate_temperature_map",
            return_value=Path("temperatura.png"),
        ) as generate:
            hydromet_temperature_map.execute_temperature_map_job(job_id)

        self.assertEqual(selected, generate.call_args.kwargs["date_interpolation"])
        self.assertEqual("20:00", generate.call_args.kwargs["end_time"])

    def test_outlying_ierse_values_are_corrected_against_etapa_references(self) -> None:
        corrected = hydromet_temperature_map._correct_remote_observations(
            {"inside": 10.2, "outside": 18.0},
            {"one": 9.0, "two": 11.0},
        )

        self.assertEqual(10.2, corrected["inside"])
        self.assertEqual(14.0, corrected["outside"])

    def test_interpolation_range_comes_from_masked_raster_not_station_extremes(self) -> None:
        features = hydromet_temperature_map._load_temperature_buffer_features()
        bounds = _expand_bounds_to_aspect(
            hydromet_temperature_map._feature_bounds(features),
            1.5,
        )
        observations = [
            (hydromet_temperature_map.TEMPERATURE_STATIONS[0], 10.0),
            (
                hydromet_temperature_map.TemperatureStation(
                    "outside",
                    -80.0,
                    -4.0,
                ),
                30.0,
            ),
        ]

        _layer, minimum, maximum = hydromet_temperature_map._interpolated_temperature_layer(
            bounds,
            features,
            observations,
            (120, 90),
            search_radius=10,
            p=2,
            n_round=2,
        )

        self.assertGreaterEqual(minimum, 10.0)
        self.assertLess(maximum, 30.0)

    def test_cressman_matches_interpolate_r_weighting_without_idw_fallback(self) -> None:
        observations = [
            (hydromet_temperature_map.TemperatureStation("near", 0.0, 0.0), 10.0),
            (hydromet_temperature_map.TemperatureStation("far", 0.05, 0.0), 20.0),
        ]

        value = hydromet_temperature_map._interpolate_r_cressman_value(
            0.01,
            0.0,
            observations,
            search_radius=10,
        )
        outside = hydromet_temperature_map._interpolate_r_cressman_value(
            1.0,
            1.0,
            observations,
            search_radius=10,
        )

        self.assertIsNotNone(value)
        self.assertGreater(value, 10.0)
        self.assertLess(value, 20.0)
        self.assertIsNone(outside)


if __name__ == "__main__":
    unittest.main()

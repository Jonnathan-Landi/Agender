from __future__ import annotations

import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend import hydromet_temperature_map
from backend.hydromet_rain_map import _expand_bounds_to_aspect


class HydrometTemperatureMapTests(unittest.TestCase):
    def test_design_uses_hydroclima_style_plot_and_axis_spacing(self) -> None:
        self.assertEqual((220, 170, 2100, 1245), hydromet_temperature_map.TEMPERATURE_PLOT_BOX)
        self.assertEqual(
            [-79.05, -79.0, -78.95, -78.9],
            hydromet_temperature_map._temperature_axis_ticks(-79.07, -78.89, 0.05),
        )
        self.assertEqual(
            [-2.92, -2.9, -2.88, -2.86, -2.84],
            hydromet_temperature_map._temperature_axis_ticks(-2.93, -2.83, 0.02),
        )

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
                    report_date=date(2026, 7, 23),
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
                root / "7/jobs/temperature-test/out/temperatura_2026-07-23.png",
                image_path,
            )
            with Image.open(image_path) as image:
                self.assertEqual((2200, 1450), image.size)
                self.assertEqual("RGB", image.mode)

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
                date(2026, 7, 23),
                "20:31",
            )

        self.assertEqual(
            {
                "SCP03_Casa Pérez": 16.34,
                "SCP17_Redondel Muñecas de Piedra": 15.8,
            },
            observations,
        )

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

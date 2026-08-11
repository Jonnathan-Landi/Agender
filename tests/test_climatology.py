from datetime import UTC, datetime, timedelta

import pytest

from backend import climatology
from backend import climatology_renderer
from backend.climatology import _rain_flow_report, _rain_report, _temperature_report, station_configuration_catalog
from backend.user_data import _allowed_keys


def test_station_catalog_contains_only_urban_and_paramo_sheets():
    result = station_configuration_catalog()

    assert [(area["id"], area["label"]) for area in result["areas"]] == [
        ("urban", "Zona Urbana"),
        ("paramo", "Páramo"),
    ]
    assert all("catalogBasin" not in area for area in result["areas"])


def test_climatology_configuration_is_allowed_for_authorized_users():
    keys = _allowed_keys({"modules": ["climatology"]})

    assert "agender.climatology.station-configuration" in keys
    assert "agender.climatology.station-configuration" not in _allowed_keys({"modules": []})


def test_climatology_renderer_and_required_styles_are_importable():
    assert climatology_renderer.ASSET_ROOT.joinpath("report.css").is_file()


@pytest.mark.parametrize(
    ("values", "month", "expected"),
    [
        ([10, 20, 70], 3, "Marzo fue el mes más lluvioso de 2026."),
        ([70, 20, 10], 3, "Marzo fue el mes más seco de 2026."),
        ([70, 10, 40], 3, "Marzo fue el segundo mes más lluvioso de 2026."),
        ([10, 70, 20, 15], 4, "Abril fue el segundo mes más seco de 2026."),
    ],
)
def test_monthly_rain_analysis_describes_the_month_rank(values, month, expected):
    rows = [{"month": month, "value": value} for month, value in enumerate(values, start=1)]

    assert climatology_renderer._monthly_rain_rank_analysis(rows, month, 2026) == expected


def test_historical_temperature_analysis_uses_executive_month_summary():
    summary = {
        "historicalComparableDays": 31,
        "historicalHotDays": 11,
        "historicalColdDays": 2,
        "hottestMaximum": 25.5,
        "hottestDate": "2026-07-22",
    }

    assert climatology_renderer._historical_range_analysis(summary, 7) == (
        "Durante julio, 11 días fueron más calientes de lo habitual y 2 días más fríos. "
        "La temperatura máxima del mes fue de 25.5 °C, registrada el 22 de julio."
    )


def test_rain_history_rank_analysis_describes_average_and_historical_position():
    summary = {"total": 19.9, "historicalMean": 20.5, "differencePercent": -2.9}
    values = [28, 21, 42, 43, 25, 6, 13, 4, 11, 16, 12, 19]
    history = [
        {"year": year, "value": value}
        for year, value in zip(range(2014, 2026), values, strict=True)
    ]

    assert climatology_renderer._rain_history_rank_analysis(summary, history, 7, 2026) == (
        "Julio 2026 acumuló 19.9 mm, ligeramente por debajo del promedio histórico de 20.5 mm, "
        "ubicándose como el sexto julio más lluvioso desde 2014."
    )


def test_temperature_and_rain_catalogs_respect_station_capabilities():
    areas = station_configuration_catalog()["areas"]

    for area in areas:
        assert area["temperatureStations"]
        assert area["rainStations"]
        assert all("meteorológica" in station["type"].casefold() for station in area["temperatureStations"])
        assert all(
            "meteorológica" in station["type"].casefold() or "pluviográfica" in station["type"].casefold()
            for station in area["rainStations"]
        )


def test_flow_sheet_station_options_are_scoped_to_each_basin():
    configuration = station_configuration_catalog()
    catalog = {station["code"]: station for station in climatology.load_station_catalog().values()}
    expected_basins = {
        "yanuncay": "Yanuncay",
        "tomebamba": "Tomebamba",
        "tarqui": "Tarqui",
        "machangara": "Machangara",
    }

    for basin in configuration["flowBasins"]:
        expected = expected_basins[basin["id"]]
        assert all(catalog[station["code"]]["basin"] == expected for station in basin["rainStations"])
        assert all(catalog[station["code"]]["basin"] == expected for station in basin["flowStations"])
        assert all(climatology.curve_for_station(station["code"]) for station in basin["flowStations"])


def test_monthly_temperature_uses_absolute_extremes_from_all_valid_records(tmp_path):
    rows = ["TIMESTAMP,TempAire_Min,TempAire_Avg,TempAire_Max"]
    for start, minimum, average, maximum in (
        (datetime(2026, 1, 15, tzinfo=UTC), 5.0, 15.0, 30.0),
        (datetime(2026, 2, 15, tzinfo=UTC), 8.0, 16.0, 25.0),
    ):
        for index in range(231):
            timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
            rows.append(f"{timestamp},{minimum},{average},{maximum}")
    source = tmp_path / "MET_Test.dat"
    source.write_text("\n".join(rows), encoding="utf-8")

    report = _temperature_report(source, "MET Test", 2026, 2, n_percent=1)
    monthly = {row["month"]: row for row in report["monthly"]}

    assert monthly[1]["maximum"] == 30.0
    assert monthly[1]["minimum"] == 5.0
    assert monthly[2]["maximum"] == 25.0
    assert monthly[2]["minimum"] == 8.0
    assert report["summary"]["monthlyMaximumDifference"] == pytest.approx(-5.0)
    assert report["summary"]["monthlyMinimumDifference"] == pytest.approx(3.0)


def test_monthly_temperature_excludes_data_after_selected_month(tmp_path):
    rows = ["TIMESTAMP,TempAire_Min,TempAire_Avg,TempAire_Max"]
    for start, average in (
        (datetime(2026, 6, 15, tzinfo=UTC), 14.0),
        (datetime(2026, 8, 15, tzinfo=UTC), 22.0),
    ):
        for index in range(231):
            timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
            rows.append(f"{timestamp},{average - 5},{average},{average + 5}")
    source = tmp_path / "MET_Test.dat"
    source.write_text("\n".join(rows), encoding="utf-8")

    report = _temperature_report(source, "MET Test", 2026, 6, n_percent=1)

    assert [row["month"] for row in report["monthly"]] == [1, 2, 3, 4, 5, 6]
    assert all(row["value"] is None for row in report["monthly"][:5])
    assert report["summary"]["rank"] == 1
    assert report["summary"]["rankTotal"] == 1


def test_rainfall_reader_preserves_decimal_measurements(tmp_path):
    rows = ["TIMESTAMP,Lluvia_Tot"]
    start = datetime(2026, 6, 1, tzinfo=UTC)
    for index in range(288):
        timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
        rainfall = 0.1 if index < 10 else 0
        rows.append(f"{timestamp},{rainfall}")
    source = tmp_path / "MET_Test.dat"
    source.write_text("\n".join(rows), encoding="utf-8")

    report = _rain_report(source, "MET Test", 2026, 6, n_percent=1)

    assert report["summary"]["total"] == pytest.approx(1.0)
    assert report["summary"]["maximum"] == pytest.approx(1.0)
    assert report["summary"]["rainDays"] == 1


def test_monthly_rain_applies_n_percent_to_expected_five_minute_records(tmp_path):
    rows = ["TIMESTAMP,Lluvia_Tot"]
    start = datetime(2026, 6, 1, tzinfo=UTC)
    for index in range(288):
        timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
        rows.append(f"{timestamp},0.1")
    source = tmp_path / "MET_Test.dat"
    source.write_text("\n".join(rows), encoding="utf-8")

    report = _rain_report(source, "MET Test", 2026, 6, n_percent=80)

    assert report["monthly"][-1]["value"] is None
    assert report["summary"]["total"] is None


def test_monthly_rain_excludes_data_after_selected_month(tmp_path):
    rows = ["TIMESTAMP,Lluvia_Tot"]
    for start in (datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC)):
        for index in range(288):
            timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
            rows.append(f"{timestamp},0.1")
    source = tmp_path / "MET_Test.dat"
    source.write_text("\n".join(rows), encoding="utf-8")

    report = _rain_report(source, "MET Test", 2026, 6, n_percent=1)

    assert [row["month"] for row in report["monthly"]] == [1, 2, 3, 4, 5, 6]
    assert all(row["value"] is None for row in report["monthly"][:5])
    assert report["summary"]["rank"] == 1
    assert report["summary"]["rankTotal"] == 1


def test_flow_sheet_converts_processed_level_avg_in_memory(tmp_path):
    start = datetime(2026, 7, 1, tzinfo=UTC)
    rain_rows = ["TIMESTAMP,Lluvia_Tot"]
    flow_rows = ["TIMESTAMP,Level_Avg"]
    for index in range(31 * 288):
        timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
        rain_rows.append(f"{timestamp},0.01")
        flow_rows.append(f"{timestamp},85")
    rain = tmp_path / "MET_Rain.dat"
    flow = tmp_path / "LIM_Tomebamba-DJ-Mazan.dat"
    rain.write_text("\n".join(rain_rows), encoding="utf-8")
    flow.write_text("\n".join(flow_rows), encoding="utf-8")

    rows = _rain_flow_report(rain, flow, "LIM_Tomebamba-DJ-Mazan", 2026, 7)

    assert len(rows) == 7
    assert all(row["rain"] is None and row["flow"] is None for row in rows[:6])
    assert rows[-1]["period"] == "2026-07"
    assert rows[-1]["rain"] == pytest.approx(89.28)
    assert rows[-1]["flow"] == pytest.approx(0.00998477)


def test_monthly_flow_chart_uses_compact_month_axis_and_soft_joined_panels():
    svg = climatology_renderer._rain_flow_svg(
        [
            {"period": "2026-01", "rain": 90.0, "flow": 4.5},
            {"period": "2026-02", "rain": 70.0, "flow": 5.0},
        ]
    )

    assert 'linearGradient id="monthly-bg"' in svg
    assert "PRECIPITACIÓN MENSUAL" not in svg
    assert "CAUDAL MENSUAL" not in svg
    assert ">Ene</text>" in svg
    assert ">Feb</text>" in svg
    assert '>Mes</text>' in svg
    assert 'font:18px Segoe UI' in svg


def test_monthly_flow_chart_does_not_connect_across_na_months():
    svg = climatology_renderer._rain_flow_svg(
        [
            {"period": "2026-01", "rain": 90.0, "flow": 4.5},
            {"period": "2026-02", "rain": None, "flow": None},
            {"period": "2026-03", "rain": 70.0, "flow": 5.0},
        ]
    )

    assert svg.count("<polyline") == 2


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([10, 8, 12], "El caudal de marzo fue el más alto desde enero de 2026."),
        ([10, 8, 12, 11], "El caudal de abril fue el segundo caudal más alto desde enero de 2026."),
        ([10, 8, 12, 7, 9], "El caudal de mayo fue el tercer caudal más bajo desde enero de 2026."),
    ],
)
def test_monthly_flow_analysis_ranks_selected_flow(values, expected):
    rows = [
        {"period": f"2026-{row_month:02d}", "rain": 100, "flow": value}
        for row_month, value in enumerate(values, start=1)
    ]

    assert climatology_renderer._rain_flow_analysis(rows, len(values)) == expected


def test_monthly_flow_analysis_does_not_describe_an_earlier_month_when_current_data_is_missing():
    rows = [
        {"period": "2026-05", "rain": 100, "flow": 10},
        {"period": "2026-06", "rain": 70, "flow": 7},
        {"period": "2026-07", "rain": None, "flow": None},
    ]

    assert climatology_renderer._rain_flow_analysis(rows, 7) == (
        "El caudal de julio no cuenta con datos suficientes para establecer su posición."
    )


def test_monthly_report_keeps_unexpected_renderer_failure_scoped_to_each_station(tmp_path, monkeypatch):
    source = tmp_path / "station.dat"
    source.write_text("TIMESTAMP,Lluvia_Tot\n", encoding="utf-8")
    catalog = {"MET_Test": {"code": "MET_Test", "basin": "Cualquiera", "type": "Meteorológica"}}
    selections = {
        area_id: {"temperature": "MET_Test", "rain": "MET_Test"}
        for area_id, _label in climatology.CLIMATE_AREAS
    }

    monkeypatch.setattr(climatology, "CLIMATOLOGY_REPORT_ROOT", tmp_path / "reports")
    monkeypatch.setattr(climatology, "load_station_catalog", lambda: catalog)
    monkeypatch.setattr(climatology, "_find_station_file", lambda *_args: source)
    monkeypatch.setattr(
        climatology,
        "_run_python_report",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("fallo inesperado del renderizador")),
    )

    result = climatology.build_exact_monthly_report(str(tmp_path), False, 2026, 7, selections)

    reports = [area["report"] for area in result["areas"]]
    assert len(reports) == 2
    assert all(report["error"] == "fallo inesperado del renderizador" for report in reports)

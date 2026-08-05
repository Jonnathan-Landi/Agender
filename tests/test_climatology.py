from datetime import UTC, datetime, timedelta

import pytest

from backend import climatology
from backend.climatology import _rain_report, _temperature_report, station_configuration_catalog


def test_station_catalog_contains_only_requested_areas_and_matching_basins():
    result = station_configuration_catalog()

    assert [area["id"] for area in result["areas"]] == ["urban", "yanuncay", "tomebamba", "tarqui", "machangara"]
    assert [area["catalogBasin"] for area in result["areas"]] == [
        "Cuenca",
        "Yanuncay",
        "Tomebamba",
        "Tarqui",
        "Machangara",
    ]


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

    report = _temperature_report(source, "MET Test", 2026, 2)
    monthly = {row["month"]: row for row in report["monthly"]}

    assert monthly[1]["maximum"] == 30.0
    assert monthly[1]["minimum"] == 5.0
    assert monthly[2]["maximum"] == 25.0
    assert monthly[2]["minimum"] == 8.0
    assert report["summary"]["monthlyMaximumDifference"] == pytest.approx(-5.0)
    assert report["summary"]["monthlyMinimumDifference"] == pytest.approx(3.0)


def test_rainfall_reader_preserves_decimal_measurements(tmp_path):
    rows = ["TIMESTAMP,Lluvia_Tot"]
    start = datetime(2026, 6, 1, tzinfo=UTC)
    for index in range(288):
        timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
        rainfall = 0.1 if index < 10 else 0
        rows.append(f"{timestamp},{rainfall}")
    source = tmp_path / "MET_Test.dat"
    source.write_text("\n".join(rows), encoding="utf-8")

    report = _rain_report(source, "MET Test", 2026, 6)

    assert report["summary"]["total"] == pytest.approx(1.0)
    assert report["summary"]["maximum"] == pytest.approx(1.0)
    assert report["summary"]["rainDays"] == 1


def test_monthly_report_keeps_unexpected_renderer_failure_scoped_to_each_station(tmp_path, monkeypatch):
    source = tmp_path / "station.dat"
    source.write_text("TIMESTAMP,Lluvia_Tot\n", encoding="utf-8")
    catalog = {
        basin: {"code": basin, "basin": basin, "type": "Meteorológica"}
        for _area_id, _label, basin in climatology.CLIMATE_AREAS
    }
    selections = {
        area_id: {"temperature": basin, "rain": basin}
        for area_id, _label, basin in climatology.CLIMATE_AREAS
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

    reports = [area[kind] for area in result["areas"] for kind in ("temperature", "rain")]
    assert len(reports) == 10
    assert all(report["error"] == "fallo inesperado del renderizador" for report in reports)

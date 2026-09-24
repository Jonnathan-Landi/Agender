from datetime import datetime, timedelta

import pytest

from backend.caudales_report import STATIONS, WEATHER_STATIONS, build_daily_flows, flow_status
from backend.discharge import curve_for_station, discharge_from_level


def test_rolling_window_and_station_curves(tmp_path):
    end = datetime(2026, 9, 23, 14)
    start = end - timedelta(hours=24)
    times = [start - timedelta(seconds=1), start, end - timedelta(hours=1), end, end + timedelta(seconds=1)]
    for _, code in STATIONS:
        (tmp_path / f"{code}.csv").write_text(
            "TIMESTAMP,Level_Avg\n" + "\n".join(f"{time.isoformat()},120" for time in times), encoding="utf-8"
        )
    result = build_daily_flows(str(tmp_path), False, end.isoformat())
    assert result["start"] == start.isoformat()
    assert [card["label"] for card in result["cards"]] == [label for label, _ in STATIONS]
    for card in result["cards"]:
        assert len(card["points"]) == 24
        assert [p["time"] for p in card["points"] if p["value"] is not None] == [
            time.isoformat() for time in times[2:4]
        ]
        assert card["current"] == pytest.approx(discharge_from_level(curve_for_station(card["station"]), 120))
        assert card["observedAt"] == end.isoformat()


def test_missing_invalid_and_outside_window_do_not_create_values(tmp_path):
    _, code = STATIONS[0]
    (tmp_path / f"{code}.csv").write_text(
        "TIMESTAMP,Level_Avg\n2026-09-23T13:00:00,NaN\n2026-09-23T14:00:01,120\n", encoding="utf-8"
    )
    result = build_daily_flows(str(tmp_path), False, "2026-09-23T14:00:00")
    assert all(card["current"] is None and card.get("error") for card in result["cards"])


def test_recursive_lookup_and_midnight_month_boundary(tmp_path):
    folder = tmp_path / "processed"
    folder.mkdir()
    _, code = STATIONS[0]
    (folder / f"{code}.csv").write_text(
        "TIMESTAMP,Level_Avg\n2026-08-31T20:00:00,120\n", encoding="utf-8"
    )
    result = build_daily_flows(str(tmp_path), True, "2026-09-01T08:30:00")
    assert result["start"] == "2026-08-31T08:00:00"
    assert any(p["value"] is not None for p in result["cards"][0]["points"])
    assert result["cards"][0]["current"] is None
    assert result["cards"][0]["status"] == "missing"
    assert build_daily_flows(str(tmp_path), False, "2026-09-01T08:30:00")["cards"][0]["current"] is None


def test_weather_uses_midnight_to_selected_time_and_correct_stations(tmp_path):
    for code in {code for _, rain, temperature in WEATHER_STATIONS for code in (rain, temperature)}:
        (tmp_path / f"{code}.csv").write_text(
            "TIMESTAMP,Lluvia_Tot,TempAire_Min\n"
            "2026-09-22T23:59:59,100,-20\n"
            "2026-09-23T00:00:00,1,10\n"
            "2026-09-23T08:00:00,2,8\n"
            "2026-09-23T14:00:00,3,12\n"
            "2026-09-23T14:00:01,100,-30\n", encoding="utf-8"
        )
    result = build_daily_flows(str(tmp_path), False, "2026-09-23T14:00:00")
    assert result["weatherStart"] == "2026-09-23T00:00:00"
    for row, (label, rain, temperature) in zip(result["weather"], WEATHER_STATIONS, strict=True):
        assert row["label"] == label
        assert row["rain"]["station"] == rain
        assert row["temperature"]["station"] == temperature
        assert row["rain"]["value"] == 6
        assert row["temperature"]["value"] == 8


def test_outdated_files_explain_last_available_date_without_using_old_values(tmp_path):
    codes = {code for _, code in STATIONS}
    codes.update(code for _, rain, temperature in WEATHER_STATIONS for code in (rain, temperature))
    for code in codes:
        (tmp_path / f"{code}.csv").write_text(
            "TIMESTAMP,Level_Avg,Lluvia_Tot,TempAire_Min\n2026-07-24T08:30:00Z,120,2,10\n",
            encoding="utf-8",
        )
    result = build_daily_flows(str(tmp_path), False, "2026-09-22T09:00:00")
    for card in result["cards"]:
        assert card["current"] is None
        assert "24/07/2026 08:30" in card["error"]
    for basin in result["weather"]:
        for metric in ("rain", "temperature"):
            assert basin[metric]["value"] is None
            assert "24/07/2026 08:30" in basin[metric]["error"]


def test_mixed_historical_and_appended_dates_use_existing_discharge_curve(tmp_path):
    (tmp_path / "LIM_Tomebamba-DJ-Mazan.dat").write_text(
        "TIMESTAMP,RECORD,TempAire_Min,TempAire_Avg,TempAire_Max,Level_Avg\n"
        "2026-07-28T11:50:00Z,1,NA,NA,NA,130.435\n"
        "2026-09-23 09:45:00,80008.0,NA,NA,NA,123.3772\n",
        encoding="utf-8",
    )
    (tmp_path / "MET_Irquis.dat").write_text(
        "TIMESTAMP,Lluvia_Tot,TempAire_Min\n"
        "2026-07-24T08:30:00Z,100,-10\n"
        "2026-09-23 00:00:00,2,9\n"
        "2026-09-23 09:45:00,3,8\n", encoding="utf-8",
    )
    result = build_daily_flows(str(tmp_path), False, "2026-09-23T10:00:00")
    card = result["cards"][0]
    assert card["observedAt"] == "2026-09-23T09:45:00"
    assert card["current"] == pytest.approx(0.00998477 * (123.3772 - 84) ** 1.59009)
    assert sum(p["value"] is not None for p in card["points"]) == 1
    assert result["weather"][2]["rain"]["value"] == 5
    assert result["weather"][2]["temperature"]["value"] == 8


@pytest.mark.parametrize(("label", "normal", "alert"), [
    ("Tomebamba", 29, 50), ("Yanuncay", 32, 50), ("Tarqui", 15, 30), ("Machángara", 19, 50),
])
def test_flow_status_boundaries(label, normal, alert):
    assert flow_status(label, normal) == "normal"
    assert flow_status(label, normal + 0.01) == "prealert"
    assert flow_status(label, alert - 0.01) == "prealert"
    assert flow_status(label, alert) == "alert"
    assert flow_status(label, None) == "missing"


def test_hourly_mean_converts_each_level_and_excludes_future_samples(tmp_path):
    code = STATIONS[0][1]
    (tmp_path / f"{code}.dat").write_text(
        "TIMESTAMP,Level_Avg\n"
        "2026-09-23 13:00:00,400\n"
        "2026-09-23 13:05:00,110\n"
        "2026-09-23 13:30:00,NA\n"
        "2026-09-23 14:00:00,150\n"
        "2026-09-23 14:05:00,500\n", encoding="utf-8",
    )
    card = build_daily_flows(str(tmp_path), False, "2026-09-23T14:00:00")["cards"][0]
    curve = curve_for_station(code)
    expected = (discharge_from_level(curve, 110) + discharge_from_level(curve, 150)) / 2
    assert card["current"] == pytest.approx(expected)
    assert card["points"][-1]["sampleCount"] == 2
    assert card["points"][-1]["time"] == "2026-09-23T14:00:00"
    assert card["status"] == flow_status("Tomebamba", expected)
    partial = build_daily_flows(str(tmp_path), False, "2026-09-23T13:45:00")["cards"][0]
    assert partial["current"] == pytest.approx(discharge_from_level(curve, 400))
    assert partial["points"][-1]["time"] == "2026-09-23T13:00:00"


def test_minutes_do_not_shift_hourly_axis_or_weather_cutoff(tmp_path):
    (tmp_path / f"{STATIONS[0][1]}.dat").write_text(
        "TIMESTAMP,Level_Avg\n2026-09-23 08:05:00,110\n"
        "2026-09-23 09:00:00,120\n2026-09-23 09:10:00,400\n", encoding="utf-8",
    )
    (tmp_path / "MET_Irquis.dat").write_text(
        "TIMESTAMP,Lluvia_Tot,TempAire_Min\n2026-09-23 09:00:00,1,10\n"
        "2026-09-23 09:10:00,2,8\n2026-09-23 09:15:00,50,-10\n", encoding="utf-8",
    )
    result = build_daily_flows(str(tmp_path), False, "2026-09-23T09:12:35")
    assert result["start"] == "2026-09-22T09:00:00"
    assert result["end"] == "2026-09-23T09:00:00"
    card = result["cards"][0]
    assert len(card["points"]) == 24
    assert all(p["time"].endswith(":00:00") for p in card["points"])
    curve = curve_for_station(STATIONS[0][1])
    assert card["current"] == pytest.approx(
        (discharge_from_level(curve, 110) + discharge_from_level(curve, 120)) / 2
    )
    assert result["weather"][2]["rain"]["value"] == 3
    assert result["weather"][2]["temperature"]["value"] == 8
    assert result["weatherEnd"] == "2026-09-23T09:12:35"

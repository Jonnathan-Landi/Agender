"""Daily discharge from the same processed files and rating curves as climatology."""
from datetime import datetime, timedelta
import math
from pathlib import Path

import polars as pl

from .climatology import _find_station_file, _read_columns
from .discharge import curve_for_station, discharge_from_level

STATIONS = (
    ("Tomebamba", "LIM_Tomebamba-DJ-Mazan"),
    ("Yanuncay", "LIM_Yanuncay-AJ-Tarqui"),
    ("Tarqui", "LIM_Tarqui-AJ-Yanuncay"),
    ("Machángara", "LIM_MachángaraLlantera"),
)
WEATHER_STATIONS = (
    ("Tomebamba", "LPL_MataderoSayausi", "MET_CebollarPTAP"),
    ("Yanuncay", "MLI_YanuncayPucan", "MLI_YanuncayPucan"),
    ("Tarqui", "MET_Irquis", "MET_Irquis"),
    ("Machángara", "MET_ElLabrado", "MET_ElLabrado"),
)
# Same continuous ranges used by the hydrometeorological report.
FLOW_THRESHOLDS = {
    "Tomebamba": (29, 50), "Yanuncay": (32, 50),
    "Tarqui": (15, 30), "Machángara": (19, 50),
}


def flow_status(label, value):
    if value is None:
        return "missing"
    normal, alert = FLOW_THRESHOLDS[label]
    return "normal" if value <= normal else "alert" if value >= alert else "prealert"


def _hourly_flows(frame, curve, start, end):
    """Mean of converted samples in (previous boundary, hour], clipped to the window."""
    buckets = {}
    observed = None
    for row in frame.iter_rows(named=True):
        time = row["timestamp"]
        if not start < time <= end:
            continue
        hour = time.replace(minute=0, second=0, microsecond=0)
        if time > hour:
            hour += timedelta(hours=1)
        boundary = min(hour, end)
        value = discharge_from_level(curve, row["Level_Avg"])
        if value is not None and math.isfinite(value):
            buckets.setdefault(boundary, []).append(value)
            observed = time
    boundary = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    points = []
    while True:
        boundary = min(boundary, end)
        values = buckets.get(boundary, [])
        points.append({
            "time": boundary.isoformat(),
            "value": sum(values) / len(values) if values else None,
            "sampleCount": len(values),
        })
        if boundary == end:
            break
        boundary += timedelta(hours=1)
    return points, observed


def _read_window(path, column, start, end):
    frame = _read_columns(path, ["TIMESTAMP", column]).with_columns(
        pl.col("timestamp").dt.replace_time_zone(None)
    )
    latest = frame["timestamp"].max()
    window = frame.filter(pl.col("timestamp").is_between(start, end)).sort("timestamp").unique(
        subset="timestamp", keep="last", maintain_order=True
    )
    if window.is_empty():
        detail = (
            f" Último registro del archivo: {latest:%d/%m/%Y %H:%M}."
            if latest else " El archivo no contiene fechas válidas."
        )
        raise ValueError(f"No hay registros en el período seleccionado.{detail}")
    return window


def _daily_weather(root, recursive, start, end, code, column):
    result = {"station": code, "value": None, "observedAt": None}
    try:
        path = _find_station_file(root, code, recursive)
        if path is None:
            raise ValueError("No se encontró el archivo procesado de la estación.")
        frame = _read_window(path, column, start, end).filter(pl.col(column).is_finite())
        if column == "Lluvia_Tot":
            frame = frame.filter(pl.col(column) >= 0)
        if frame.is_empty():
            raise ValueError("Sin datos válidos desde las 00:00 hasta la hora seleccionada.")
        result["value"] = frame[column].sum() if column == "Lluvia_Tot" else frame[column].min()
        result["observedAt"] = frame["timestamp"].max().isoformat()
    except (ValueError, OSError, pl.exceptions.PolarsError) as error:
        result["error"] = str(error)
    return result


def build_daily_flows(data_root: str, recursive: bool, end_value: str) -> dict:
    end = datetime.fromisoformat(end_value)
    if end.tzinfo is not None:
        raise ValueError("Seleccione fecha y hora local sin zona horaria.")
    selected_end = end
    end = end.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=24)
    root = Path(data_root)
    if not root.is_dir():
        raise ValueError("La carpeta de datos procesados no está disponible.")
    cards = []
    for label, code in STATIONS:
        card = {
            "label": label, "station": code, "points": [], "current": None, "observedAt": None,
            "status": "missing", "lowThreshold": 2.0, "dryThreshold": 1.2,
        }
        try:
            path = _find_station_file(root, code, recursive)
            if path is None:
                raise ValueError("No se encontró el archivo procesado de la estación.")
            curve = curve_for_station(code)
            if not curve:
                raise ValueError("La estación no tiene curva de descarga.")
            # The reader tags station wall-clock timestamps UTC without shifting them.
            frame = _read_window(path, "Level_Avg", start, end)
            card["points"], observed = _hourly_flows(frame, curve, start, end)
            card["current"] = card["points"][-1]["value"]
            card["observedAt"] = observed.isoformat() if observed else None
            card["status"] = flow_status(label, card["current"])
            if card["current"] is None:
                card["error"] = "Sin datos válidos en la hora seleccionada."
        except (ValueError, OSError, pl.exceptions.PolarsError) as error:
            card["error"] = str(error)
        cards.append(card)
    midnight = selected_end.replace(hour=0, minute=0, second=0, microsecond=0)
    weather = [
        {
            "label": label,
            "rain": _daily_weather(root, recursive, midnight, selected_end, rain, "Lluvia_Tot"),
            "temperature": _daily_weather(root, recursive, midnight, selected_end, temperature, "TempAire_Min"),
        }
        for label, rain, temperature in WEATHER_STATIONS
    ]
    return {
        "start": start.isoformat(), "end": end.isoformat(), "cards": cards,
        "weatherStart": midnight.isoformat(), "weatherEnd": selected_end.isoformat(), "weather": weather,
    }

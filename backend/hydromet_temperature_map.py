from __future__ import annotations

import csv
import io
import json
import math
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .config import APP_DATA_DIR
from .job_registry import JobRegistry
from .hydromet_rain_map import (
    MAP_SIZE,
    SPANISH_MONTHS,
    SPANISH_WEEKDAYS,
    _basemap,
    _fallback_basemap,
    _feature_bounds,
    _feature_rings,
    _font,
    _grid_size,
    _map_point,
    _polygon_mask,
    _png_data_uri,
    _draw_outer_boundary,
)

REPORT_ROOT = APP_DATA_DIR / "reports" / "hydromet-network"
ASSET_DIR = Path(__file__).resolve().parent / "data" / "hydromet_temperature_map"
BUFFER_PATH = ASSET_DIR / "buffer.geojson"
IERSE_MONTH_URL = (
    "https://ierse.uazuay.edu.ec/proyectos/meteorologia-continua/"
    "lib/exportDataMonth.php"
)
DEFAULT_SEARCH_RADIUS_KM = 10.0
DEFAULT_IDW_POWER = 2.0
DEFAULT_GRID_RESOLUTION_KM = 0.01
DEFAULT_ROUND_DIGITS = 2
TEMPERATURE_PLOT_BOX = (170, 150, 2180, 1160)
TEMPERATURE_PLOT_SIZE = (
    TEMPERATURE_PLOT_BOX[2] - TEMPERATURE_PLOT_BOX[0],
    TEMPERATURE_PLOT_BOX[3] - TEMPERATURE_PLOT_BOX[1],
)


@dataclass(frozen=True)
class TemperatureStation:
    name: str
    longitude: float
    latitude: float
    elevation: float | None = None


# Las 15 coordenadas originales de HydroClima (UTM 17S) transformadas a WGS84.
TEMPERATURE_STATIONS = (
    TemperatureStation("SCP00_Universidad del Azuay (A1)", -78.99983382, -2.91849651),
    TemperatureStation("SCP03_Casa Pérez", -79.00640582, -2.90416827),
    TemperatureStation("SCP04_Calle Larga", -79.00442189, -2.90167831),
    TemperatureStation("SCP06_Remigio Crespo", -79.01160042, -2.90549755),
    TemperatureStation("SCP07_Estadio Serrano Aguilar", -79.00498749, -2.90733935),
    TemperatureStation("SCP08_Mercado El Arenal", -79.02575573, -2.89791843),
    TemperatureStation("SCP09_Parque Industrial", -78.98151654, -2.87576984),
    TemperatureStation("SCP13_Av. Don Bosco", -79.03102405, -2.91330763),
    TemperatureStation("SCP16_Av. Los Andes", -78.97622277, -2.89151059),
    TemperatureStation("SCP17_Redondel Muñecas de Piedra", -78.95635706, -2.88373544),
    TemperatureStation("MET_TixánPTAP", -78.99384018, -2.83288427),
    TemperatureStation("MET_SayausiPTAP", -79.06880043, -2.86013743),
    TemperatureStation("MET_CebollarPTAP", -79.01876813, -2.88522984),
    TemperatureStation("MET_ElValle", -78.96208451, -2.94547593),
    TemperatureStation("MET_UcubambaPTAR", -78.94153855, -2.87578848),
)
MANUAL_STATION_PREFIX = "MET_"
IERSE_STATION_ALIASES = {
    "SCP17_Monumento a la Familia": "SCP17_Redondel Muñecas de Piedra",
}

COOL_STOPS = (
    "#081D58", "#253494", "#225EA8", "#1D91C0", "#41B6C4",
    "#7FCDBB", "#C7E9B4", "#EDF8B1", "#FFFFD9",
)
WARM_STOPS = (
    "#FFFFCC", "#FFEDA0", "#FED976", "#FEB24C", "#FD8D3C",
    "#FC4E2A", "#E31A1C", "#BD0026", "#800026",
)

_jobs = JobRegistry()


def station_names() -> tuple[str, ...]:
    return tuple(station.name for station in TEMPERATURE_STATIONS)


def manual_station_names() -> tuple[str, ...]:
    return tuple(name for name in station_names() if name.startswith(MANUAL_STATION_PREFIX))


def create_temperature_map_job(
    user_id: int,
    date_interpolation: datetime,
    start_time: str,
    end_time: str,
    observations: dict[str, float | None],
    parameters: dict[str, float | int] | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    _jobs.add(job_id, {
        "jobId": job_id,
        "userId": int(user_id),
        "status": "queued",
        "message": "Mapa en cola",
        "dateInterpolation": date_interpolation.isoformat(),
        "startTime": start_time,
        "endTime": end_time,
        "observations": observations.copy(),
        "parameters": (parameters or {}).copy(),
        "imagePath": None,
        "error": None,
    })
    return job_id


def execute_temperature_map_job(job_id: str) -> None:
    job = _jobs.get(job_id)
    if not job:
        return
    _jobs.update(job_id, status="running", message="Generando mapa de temperaturas")
    try:
        image_path = generate_temperature_map(
            user_id=job["userId"],
            job_id=job_id,
            date_interpolation=datetime.fromisoformat(job["dateInterpolation"]),
            start_time=job["startTime"],
            end_time=job["endTime"],
            observations=job["observations"],
            **job.get("parameters", {}),
        )
        _jobs.update(
            job_id,
            status="completed",
            message="Mapa generado",
            imagePath=str(image_path),
        )
    except Exception as error:
        _jobs.update(
            job_id,
            status="failed",
            message="No se pudo generar el mapa",
            error=str(error),
        )


def temperature_map_job(job_id: str, user_id: int) -> dict[str, Any] | None:
    job = _jobs.get(job_id)
    if not job or job["userId"] != int(user_id):
        return None
    return {
        "jobId": job["jobId"],
        "status": job["status"],
        "message": job["message"],
        "dateInterpolation": job["dateInterpolation"],
        "error": job["error"],
    }


def temperature_map_image(job_id: str, user_id: int) -> Path | None:
    job = _jobs.get(job_id)
    if not job or job["userId"] != int(user_id) or job["status"] != "completed":
        return None
    image_path = Path(job["imagePath"])
    try:
        image_path.resolve().relative_to((REPORT_ROOT / str(user_id)).resolve())
    except ValueError:
        return None
    return image_path if image_path.is_file() else None


def generate_temperature_map(
    *,
    user_id: int,
    job_id: str,
    date_interpolation: datetime,
    start_time: str,
    end_time: str,
    observations: dict[str, float | None],
    fetch_basemap: bool = True,
    search_radius: float = DEFAULT_SEARCH_RADIUS_KM,
    p: float = DEFAULT_IDW_POWER,
    grid_resolution: float = DEFAULT_GRID_RESOLUTION_KM,
    n_round: int = DEFAULT_ROUND_DIGITS,
    remote_observations: dict[str, float] | None = None,
) -> Path:
    manual_observations = {
        name: observations.get(name)
        for name in manual_station_names()
    }
    remote = (
        remote_observations
        if remote_observations is not None
        else fetch_ierse_temperature_observations(date_interpolation)
    )
    corrected_remote = _correct_remote_observations(remote, manual_observations)
    combined_observations = {**corrected_remote, **manual_observations}
    available = [
        (station, combined_observations.get(station.name))
        for station in TEMPERATURE_STATIONS
        if combined_observations.get(station.name) is not None
    ]
    if not available:
        raise ValueError("Ingresa al menos un valor de temperatura para generar el mapa.")

    output_dir = REPORT_ROOT / str(user_id) / "jobs" / job_id / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_date = date_interpolation.date()
    image_path = output_dir / f"temperatura_{report_date.isoformat()}.svg"

    features = _load_temperature_buffer_features()
    bounds = _temperature_map_bounds(features)
    background = (
        _basemap(bounds, TEMPERATURE_PLOT_SIZE)
        if fetch_basemap
        else _fallback_basemap(TEMPERATURE_PLOT_SIZE)
    )
    grid_size = _grid_size(bounds, grid_resolution)
    temperature_layer, minimum, maximum = _interpolated_temperature_layer(
        bounds,
        features,
        available,
        grid_size,
        search_radius=search_radius,
        p=p,
        n_round=n_round,
    )
    temperature_layer = temperature_layer.resize(
        TEMPERATURE_PLOT_SIZE,
        Image.Resampling.BILINEAR,
    )
    map_image = Image.alpha_composite(background.convert("RGBA"), temperature_layer)
    image_path.write_text(
        _compose_temperature_design_svg(
            map_image,
            bounds,
            features,
            report_date,
            start_time,
            end_time,
            minimum,
            maximum,
        ),
        encoding="utf-8",
    )
    return image_path


def fetch_ierse_temperature_observations(
    date_interpolation: datetime,
    *,
    timeout_seconds: float = 90,
) -> dict[str, float]:
    payload = urllib.parse.urlencode(
        {
            "year": str(date_interpolation.year),
            "month": f"{date_interpolation.month:02d}",
            "monthName": date_interpolation.strftime("%B"),
            "varmet": "TC",
        }
    ).encode("ascii")
    request = urllib.request.Request(
        IERSE_MONTH_URL,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Agender/1.13",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content = response.read(8 * 1024 * 1024)
    except OSError as error:
        raise ValueError(
            "No fue posible descargar las temperaturas de las estaciones IERSE."
        ) from error

    interpolation_hour = date_interpolation.replace(minute=0, second=0, microsecond=0)
    target_timestamp = interpolation_hour.strftime("%Y-%m-%d %H:00:00")
    observations: dict[str, float] = {}
    try:
        rows = csv.DictReader(
            io.StringIO(content.decode("utf-8-sig")),
            delimiter=";",
        )
        for row in rows:
            if row.get("timestamp", "").strip('"') != target_timestamp:
                continue
            source_name = row.get("id_nombre", "").strip().strip('"')
            station = IERSE_STATION_ALIASES.get(source_name, source_name)
            if station not in station_names() or station.startswith(MANUAL_STATION_PREFIX):
                continue
            raw_value = row.get("avgTC", "").strip()
            if raw_value:
                observations[station] = float(raw_value)
    except (UnicodeDecodeError, ValueError, csv.Error) as error:
        raise ValueError("La respuesta de IERSE no tiene el formato esperado.") from error
    if not observations:
        raise ValueError(
            "IERSE no dispone de datos para "
            f"{interpolation_hour.strftime('%Y-%m-%d a las %H:00')}."
        )
    return observations


def _correct_remote_observations(
    remote: dict[str, float],
    references: dict[str, float | None],
) -> dict[str, float]:
    values = [float(value) for value in references.values() if value is not None]
    if not values:
        return remote.copy()
    reference_minimum = min(values)
    reference_maximum = max(values)
    reference_mean = sum(values) / len(values)
    return {
        station: (
            (float(value) + reference_mean) / 2
            if float(value) < reference_minimum or float(value) > reference_maximum
            else float(value)
        )
        for station, value in remote.items()
    }


def _load_temperature_buffer_features() -> list[dict[str, Any]]:
    payload = json.loads(BUFFER_PATH.read_text(encoding="utf-8"))
    return payload["features"]


def _temperature_map_bounds(
    features: list[dict[str, Any]],
) -> tuple[float, float, float, float]:
    """Match HydroClima's close urban framing while preserving geographic aspect."""
    west, south, east, north = _feature_bounds(features)
    padding = 0.009
    west, south, east, north = (
        west - padding,
        south - padding,
        east + padding,
        north + padding,
    )
    return west, south, east, north


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[int, int],
    end: tuple[int, int],
) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy))


def _feature_label_point(
    feature: dict[str, Any],
    bounds: tuple[float, float, float, float],
    size: tuple[int, int],
) -> tuple[tuple[int, int], Image.Image]:
    rings = _feature_rings(feature)
    pixel_rings = [
        [_map_point(*point, bounds, size) for point in ring]
        for ring in rings
        if len(ring) > 2
    ]
    if not pixel_rings:
        return (size[0] // 2, size[1] // 2), Image.new("L", size, 0)
    mask = Image.new("L", size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.polygon(pixel_rings[0], fill=255)
    for hole in pixel_rings[1:]:
        mask_draw.polygon(hole, fill=0)
    bbox = mask.getbbox()
    if not bbox:
        return (size[0] // 2, size[1] // 2), mask
    edges = [
        (ring[index], ring[(index + 1) % len(ring)])
        for ring in pixel_rings
        for index in range(len(ring))
    ]
    step = max(8, min(size) // 100)
    best_point = ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
    best_distance = -1.0
    pixels = mask.load()
    for y in range(bbox[1], bbox[3], step):
        for x in range(bbox[0], bbox[2], step):
            if not pixels[x, y]:
                continue
            distance = min(_point_segment_distance((x, y), start, end) for start, end in edges)
            if distance > best_distance:
                best_distance = distance
                best_point = (x, y)
    return best_point, mask


def _label_fits_feature(
    mask: Image.Image,
    center: tuple[int, int],
    width: int,
    height: int,
) -> bool:
    left = round(center[0] - width / 2)
    top = round(center[1] - height / 2)
    right = left + width - 1
    bottom = top + height - 1
    samples = (
        (left, top), ((left + right) // 2, top), (right, top),
        (left, (top + bottom) // 2), (right, (top + bottom) // 2),
        (left, bottom), ((left + right) // 2, bottom), (right, bottom),
    )
    pixels = mask.load()
    return all(
        0 <= x < mask.width and 0 <= y < mask.height and pixels[x, y]
        for x, y in samples
    )


def _interpolated_temperature_layer(
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
    observations: list[tuple[TemperatureStation, float | None]],
    size: tuple[int, int],
    *,
    search_radius: float,
    p: float,
    n_round: int,
) -> tuple[Image.Image, float, float]:
    west, south, east, north = bounds
    mask = _polygon_mask(bounds, features, size)
    mask_pixels = mask.load()
    interpolated: list[list[float | None]] = []
    values_inside_mask: list[float] = []
    for y in range(size[1]):
        latitude = north - (y / max(1, size[1] - 1)) * (north - south)
        row = []
        for x in range(size[0]):
            if not mask_pixels[x, y]:
                row.append(None)
                continue
            longitude = west + (x / max(1, size[0] - 1)) * (east - west)
            raw_value = _interpolate_r_cressman_value(
                longitude,
                latitude,
                observations,
                search_radius=search_radius,
            )
            value = round(raw_value, n_round) if raw_value is not None else None
            row.append(value)
            if value is not None:
                values_inside_mask.append(value)
        interpolated.append(row)
    if not values_inside_mask:
        raise ValueError("El área urbana no contiene celdas interpolables.")
    minimum = min(values_inside_mask)
    maximum = max(values_inside_mask)

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = layer.load()
    palette = _temperature_palette(maximum)
    for y in range(size[1]):
        for x in range(size[0]):
            value = interpolated[y][x]
            if value is not None:
                pixels[x, y] = (*_gradient_color(value, minimum, maximum, palette), 145)
    layer.putalpha(Image.eval(mask, lambda value: round(value * 145 / 255)))
    return layer, minimum, maximum


def _interpolate_r_cressman_value(
    longitude: float,
    latitude: float,
    observations: list[tuple[TemperatureStation, float | None]],
    *,
    search_radius: float,
) -> float | None:
    cosine = math.cos(math.radians(latitude))
    radius_squared = search_radius**2
    weighted_sum = 0.0
    weight_total = 0.0
    for station, raw_value in observations:
        if raw_value is None:
            continue
        dx = (longitude - station.longitude) * 111.32 * cosine
        dy = (latitude - station.latitude) * 110.57
        distance_squared = dx * dx + dy * dy
        if distance_squared > radius_squared:
            continue
        weight = (
            (radius_squared - distance_squared)
            / (radius_squared + distance_squared)
        )
        weighted_sum += weight * float(raw_value)
        weight_total += weight
    return weighted_sum / weight_total if weight_total else None


def _gradient_color(
    value: float,
    minimum: float,
    maximum: float,
    stops: tuple[str, ...],
) -> tuple[int, int, int]:
    if maximum <= minimum:
        position = 0.5
    else:
        position = max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))
    scaled = position * (len(stops) - 1)
    index = min(len(stops) - 2, int(scaled))
    fraction = scaled - index
    first = tuple(int(stops[index][offset:offset + 2], 16) for offset in (1, 3, 5))
    second = tuple(int(stops[index + 1][offset:offset + 2], 16) for offset in (1, 3, 5))
    return tuple(
        round(a + (b - a) * fraction)
        for a, b in zip(first, second, strict=True)
    )


def _temperature_palette(maximum: float) -> tuple[str, ...]:
    return COOL_STOPS if maximum < 17 else WARM_STOPS


def _temperature_axis_ticks(start: float, end: float, step: float) -> list[float]:
    first = math.ceil((start - 1e-9) / step) * step
    ticks = []
    value = first
    while value <= end + 1e-9:
        ticks.append(round(value, 10))
        value += step
    return ticks


def _temperature_svg_path(
    feature: dict[str, Any],
    bounds: tuple[float, float, float, float],
) -> str:
    commands: list[str] = []
    left, top, _right, _bottom = TEMPERATURE_PLOT_BOX
    for ring in _feature_rings(feature):
        points = [_map_point(*point, bounds, TEMPERATURE_PLOT_SIZE) for point in ring]
        if points:
            commands.append(
                "M "
                + " L ".join(f"{left + x},{top + y}" for x, y in points)
                + " Z"
            )
    return " ".join(commands)


def _compose_temperature_design_svg(
    map_image: Image.Image,
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
    report_date: date,
    start_time: str,
    end_time: str,
    minimum: float,
    maximum: float,
) -> str:
    left, top, right, bottom = TEMPERATURE_PLOT_BOX
    raster_map = map_image.copy()
    _draw_outer_boundary(raster_map, bounds, features)
    kind = "mínima" if maximum < 17 else "máxima"
    title_line = (
        f"{SPANISH_WEEKDAYS[report_date.weekday()].capitalize()} "
        f"{report_date.day} de {SPANISH_MONTHS[report_date.month - 1]} {report_date.year}, "
        f"{start_time} - {end_time}"
    )
    palette = _temperature_palette(maximum)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{MAP_SIZE[0]}" '
        f'height="{MAP_SIZE[1]}" viewBox="0 0 {MAP_SIZE[0]} {MAP_SIZE[1]}">',
        "<defs>",
        '<linearGradient id="temperature-scale" x1="0" y1="1" x2="0" y2="0">',
    ]
    for index, color in enumerate(palette):
        parts.append(
            f'<stop offset="{index / (len(palette) - 1):.4f}" stop-color="{color}"/>'
        )
    parts.extend([
        "</linearGradient>",
        "</defs>",
        "<style>"
        "text{font-family:'Segoe UI',Arial,sans-serif;text-rendering:geometricPrecision}"
        ".district{fill:#fff;font-weight:600}"
        ".tick{fill:#111;font-size:32px;font-weight:700}"
        "</style>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<image x="{left}" y="{top}" width="{TEMPERATURE_PLOT_SIZE[0]}" '
        f'height="{TEMPERATURE_PLOT_SIZE[1]}" href="{_png_data_uri(raster_map)}" '
        'preserveAspectRatio="none"/>',
    ])
    for feature in features:
        path = _temperature_svg_path(feature, bounds)
        if path:
            parts.append(
                f'<path d="{path}" fill="none" stroke="#080808" stroke-width="4" '
                'stroke-dasharray="13 10" stroke-linecap="round" stroke-linejoin="round"/>'
            )
    vertical = {"Gil Ramirez Dávalos", "El Sagrario", "San Blas"}
    small = vertical | {"Cañaribamba"}
    for feature in features:
        name = str(feature.get("properties", {}).get("name", "")).strip()
        if not name:
            continue
        (x, y), feature_mask = _feature_label_point(
            feature,
            bounds,
            TEMPERATURE_PLOT_SIZE,
        )
        label_lines = [part.upper() for part in name.split()]
        label = "\n".join(label_lines)
        target_size = 27 if name in small else 32
        font_size = target_size
        measure = ImageDraw.Draw(Image.new("L", (1, 1)))
        while font_size > 18:
            box = measure.multiline_textbbox(
                (0, 0),
                label,
                font=_font(font_size),
                spacing=0,
                align="center",
            )
            width = box[2] - box[0] + 8
            height = box[3] - box[1] + 8
            fitted = (height, width) if name in vertical else (width, height)
            if _label_fits_feature(feature_mask, (x, y), *fitted):
                break
            font_size -= 1
        transform = (
            f' transform="rotate(90 {left + x} {top + y})"'
            if name in vertical
            else ""
        )
        line_height = font_size * 0.9
        first_y = top + y - line_height * (len(label_lines) - 1) / 2
        tspans = "".join(
            f'<tspan x="{left + x}" y="{first_y + index * line_height}">'
            f'{escape(line)}</tspan>'
            for index, line in enumerate(label_lines)
        )
        parts.append(
            f'<text class="district" x="{left + x}" y="{top + y}" '
            f'font-size="{font_size}" text-anchor="middle" dominant-baseline="middle"'
            f'{transform}>{tspans}</text>'
        )
    parts.extend([
        f'<text x="{MAP_SIZE[0] / 2}" y="58" text-anchor="middle" '
        f'font-size="54" font-weight="700">Temperatura {kind} en Cuenca:</text>',
        f'<text x="{MAP_SIZE[0] / 2}" y="116" text-anchor="middle" '
        f'font-size="54" font-weight="700">{escape(title_line)}</text>',
    ])
    west, south, east, north = bounds
    for longitude in _temperature_axis_ticks(west, east, 0.05):
        x = left + (longitude - west) / (east - west) * (right - left)
        parts.append(f'<line x1="{x}" y1="{bottom}" x2="{x}" y2="{bottom + 22}" stroke="#2b2b2b" stroke-width="7"/>')
        parts.append(f'<text class="tick" x="{x}" y="{bottom + 65}" text-anchor="middle">{abs(longitude):.2f}°W</text>')
    for latitude in _temperature_axis_ticks(south, north, 0.02):
        y = bottom - (latitude - south) / (north - south) * (bottom - top)
        parts.append(f'<line x1="{left - 22}" y1="{y}" x2="{left}" y2="{y}" stroke="#2b2b2b" stroke-width="7"/>')
        parts.append(
            f'<text class="tick" x="{left - 28}" y="{y}" text-anchor="end" '
            f'dominant-baseline="middle">{abs(latitude):.2f}°S</text>'
        )
    parts.extend([
        f'<text x="{(left + right) / 2}" y="{MAP_SIZE[1] - 20}" text-anchor="middle" '
        'font-size="43" font-weight="700">Longitud (°W)</text>',
        f'<text x="55" y="{(top + bottom) / 2}" text-anchor="middle" font-size="43" '
        f'font-weight="700" transform="rotate(-90 55 {(top + bottom) / 2})">Latitud (°S)</text>',
    ])
    center_x, center_y = left + 190, top + 190
    parts.extend([
        f'<text x="{center_x}" y="{top + 75}" text-anchor="middle" fill="#fff" font-size="72">N</text>',
        f'<circle cx="{center_x}" cy="{center_y + 15}" r="72" fill="none" stroke="#050505" stroke-width="4"/>',
        f'<path d="M {center_x},{center_y - 88} L {center_x - 55},{center_y + 72} '
        f'L {center_x},{center_y + 32} Z" fill="#fff" stroke="#050505" stroke-width="3"/>',
        f'<path d="M {center_x},{center_y - 88} L {center_x + 55},{center_y + 72} '
        f'L {center_x},{center_y + 32} Z" fill="#eee" stroke="#050505" stroke-width="3"/>',
    ])
    panel_width = round((right - left) * 0.24)
    panel_height = round((bottom - top) * 0.48)
    panel_right = right - round((right - left) * 0.001)
    panel_bottom = bottom - round((bottom - top) * 0.001)
    panel_left, panel_top = panel_right - panel_width, panel_bottom - panel_height
    margin_x = panel_width * 0.05
    margin_bottom = panel_height * 0.04
    margin_top = panel_height * 0.06
    title_space = panel_height * 0.20
    bar_left = panel_left + margin_x
    bar_right = bar_left + panel_width * 0.23
    bar_top = panel_top + margin_top + title_space
    bar_bottom = panel_bottom - margin_bottom
    parts.extend([
        f'<rect x="{panel_left}" y="{panel_top}" width="{panel_width}" height="{panel_height}" '
        'fill="#f8f8f8" fill-opacity=".70"/>',
        f'<text x="{panel_left + panel_width / 2}" y="{panel_top + margin_top + 30}" text-anchor="middle" '
        f'font-size="34" font-weight="700">Temperatura {kind} (°C)</text>',
        f'<rect x="{bar_left}" y="{bar_top}" width="{bar_right - bar_left}" height="{bar_bottom - bar_top}" '
        'fill="url(#temperature-scale)" stroke="#222" stroke-width="2"/>',
    ])
    for index in range(5):
        ratio = index / 4
        y = bar_bottom - ratio * (bar_bottom - bar_top)
        value = minimum + ratio * (maximum - minimum)
        parts.append(f'<line x1="{bar_right}" y1="{y}" x2="{bar_right + 12}" y2="{y}" stroke="#222" stroke-width="2"/>')
        parts.append(
            f'<text x="{bar_right + panel_width * 0.07}" y="{y}" '
            f'dominant-baseline="middle" font-size="46" font-weight="700">{value:.2f}</text>'
        )
    from .hydromet_rain_map import LOGO_PATH
    if LOGO_PATH.is_file():
        with Image.open(LOGO_PATH) as logo:
            logo_uri = _png_data_uri(logo.convert("RGBA"))
        parts.extend([
            f'<rect x="{left + (right-left) * 0.65}" y="{top}" width="{(right-left) * 0.35}" '
            f'height="{(bottom-top) * 0.10}" fill="#fff" fill-opacity=".70"/>',
            f'<image x="{left + (right-left) * 0.65}" y="{top}" width="{(right-left) * 0.35}" '
            f'height="{(bottom-top) * 0.10}" '
            f'href="{logo_uri}" preserveAspectRatio="xMidYMid meet"/>',
        ])
    parts.append(
        f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" '
        'fill="none" stroke="#050505" stroke-width="8"/>'
    )
    parts.append("</svg>")
    return "".join(parts)

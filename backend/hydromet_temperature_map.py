from __future__ import annotations

import csv
import io
import json
import math
import threading
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .config import APP_DATA_DIR
from .hydromet_rain_map import (
    MAP_SIZE,
    SPANISH_MONTHS,
    SPANISH_WEEKDAYS,
    _basemap,
    _draw_logo,
    _fallback_basemap,
    _feature_bounds,
    _font,
    _grid_size,
    _polygon_mask,
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
TEMPERATURE_PLOT_BOX = (220, 170, 2100, 1245)
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

COOL_STOPS = ("#081D58", "#225EA8", "#1D91C0", "#7FCDBB", "#FFFFD9")
WARM_STOPS = ("#FFFFCC", "#FED976", "#FD8D3C", "#E31A1C", "#800026")

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def station_names() -> tuple[str, ...]:
    return tuple(station.name for station in TEMPERATURE_STATIONS)


def manual_station_names() -> tuple[str, ...]:
    return tuple(name for name in station_names() if name.startswith(MANUAL_STATION_PREFIX))


def create_temperature_map_job(
    user_id: int,
    report_date: date,
    start_time: str,
    end_time: str,
    observations: dict[str, float | None],
    parameters: dict[str, float | int] | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "jobId": job_id,
            "userId": int(user_id),
            "status": "queued",
            "message": "Mapa en cola",
            "reportDate": report_date.isoformat(),
            "startTime": start_time,
            "endTime": end_time,
            "observations": observations.copy(),
            "parameters": (parameters or {}).copy(),
            "imagePath": None,
            "error": None,
        }
    return job_id


def execute_temperature_map_job(job_id: str) -> None:
    job = _job_copy(job_id)
    if not job:
        return
    _update_job(job_id, status="running", message="Generando mapa de temperaturas")
    try:
        image_path = generate_temperature_map(
            user_id=job["userId"],
            job_id=job_id,
            report_date=date.fromisoformat(job["reportDate"]),
            start_time=job["startTime"],
            end_time=job["endTime"],
            observations=job["observations"],
            **job.get("parameters", {}),
        )
        _update_job(
            job_id,
            status="completed",
            message="Mapa generado",
            imagePath=str(image_path),
        )
    except Exception as error:
        _update_job(
            job_id,
            status="failed",
            message="No se pudo generar el mapa",
            error=str(error),
        )


def temperature_map_job(job_id: str, user_id: int) -> dict[str, Any] | None:
    job = _job_copy(job_id)
    if not job or job["userId"] != int(user_id):
        return None
    return {
        "jobId": job["jobId"],
        "status": job["status"],
        "message": job["message"],
        "reportDate": job["reportDate"],
        "error": job["error"],
    }


def temperature_map_image(job_id: str, user_id: int) -> Path | None:
    job = _job_copy(job_id)
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
    report_date: date,
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
        else fetch_ierse_temperature_observations(report_date, end_time)
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
    image_path = output_dir / f"temperatura_{report_date.isoformat()}.png"

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
    _draw_temperature_boundaries(map_image, bounds, features)
    _draw_temperature_feature_labels(map_image, bounds, features)
    designed_map = _compose_temperature_design(
        map_image,
        bounds,
        report_date,
        start_time,
        end_time,
        minimum,
        maximum,
    )
    designed_map.convert("RGB").save(image_path, format="PNG", optimize=True)
    return image_path


def fetch_ierse_temperature_observations(
    report_date: date,
    end_time: str,
    *,
    timeout_seconds: float = 90,
) -> dict[str, float]:
    payload = urllib.parse.urlencode(
        {
            "year": str(report_date.year),
            "month": f"{report_date.month:02d}",
            "monthName": report_date.strftime("%B"),
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

    hour = end_time.split(":", 1)[0]
    target_timestamp = f"{report_date.isoformat()} {hour}:00:00"
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
            f"IERSE no dispone de datos para {report_date.isoformat()} a las {hour}:00."
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
    padding = 0.0015
    west, south, east, north = (
        west - padding,
        south - padding,
        east + padding,
        north + padding,
    )
    target_aspect = TEMPERATURE_PLOT_SIZE[0] / TEMPERATURE_PLOT_SIZE[1]
    width = east - west
    height = north - south
    latitude_scale = math.cos(math.radians((south + north) / 2))
    geographic_aspect = width * latitude_scale / height
    if geographic_aspect < target_aspect:
        desired_width = height * target_aspect / latitude_scale
        extra = (desired_width - width) / 2
        west -= extra
        east += extra
    else:
        desired_height = width * latitude_scale / target_aspect
        extra = (desired_height - height) / 2
        south -= extra
        north += extra
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
    from .hydromet_rain_map import _feature_rings, _map_point

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


def _draw_temperature_feature_labels(
    image: Image.Image,
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
) -> None:
    vertical = {"Gil Ramirez Dávalos", "El Sagrario", "San Blas"}
    small = vertical | {"Cañaribamba"}
    draw = ImageDraw.Draw(image, "RGBA")
    for feature in features:
        name = str(feature.get("properties", {}).get("name", "")).strip()
        if not name:
            continue
        (x, y), feature_mask = _feature_label_point(feature, bounds, image.size)
        label = "\n".join(part.upper() for part in name.split())
        target_size = 27 if name in small else 32
        for font_size in range(target_size, 17, -1):
            font = _font(font_size)
            text_box = draw.multiline_textbbox(
                (0, 0), label, font=font, spacing=0, align="center"
            )
            width = round(text_box[2] - text_box[0] + 8)
            height = round(text_box[3] - text_box[1] + 8)
            fitted_width, fitted_height = (
                (height, width) if name in vertical else (width, height)
            )
            if _label_fits_feature(feature_mask, (x, y), fitted_width, fitted_height):
                break
        label_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(label_image).multiline_text(
            (4 - text_box[0], 4 - text_box[1]),
            label,
            fill=(255, 255, 255, 255),
            font=font,
            spacing=0,
            align="center",
        )
        if name in vertical:
            label_image = label_image.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
        image.alpha_composite(
            label_image,
            (round(x - label_image.width / 2), round(y - label_image.height / 2)),
        )


def _draw_temperature_boundaries(
    image: Image.Image,
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
) -> None:
    from .hydromet_rain_map import _draw_dashed_line, _feature_rings, _map_point

    draw = ImageDraw.Draw(image, "RGBA")
    for feature in features:
        for ring in _feature_rings(feature):
            points = [_map_point(*point, bounds, image.size) for point in ring]
            if len(points) > 1:
                _draw_dashed_line(draw, points, fill=(8, 8, 8, 255), width=4, dash=13, gap=10)

    mask = _polygon_mask(bounds, features, image.size)
    outer = ImageChops.difference(
        mask.filter(ImageFilter.MaxFilter(11)),
        mask.filter(ImageFilter.MinFilter(11)),
    )
    image.paste((5, 5, 5, 255), mask=outer)


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


def _draw_temperature_axes(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    bounds: tuple[float, float, float, float],
) -> None:
    west, south, east, north = bounds
    left, top, right, bottom = TEMPERATURE_PLOT_BOX
    tick_font = _font(42, bold=True)
    axis_font = _font(56, bold=True)
    for longitude in _temperature_axis_ticks(west, east, 0.05):
        x = left + (longitude - west) / (east - west) * (right - left)
        draw.line((x, bottom, x, bottom + 22), fill="#2b2b2b", width=7)
        label = f"{abs(longitude):.2f}°W"
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text(
            (x - (box[2] - box[0]) / 2, bottom + 31),
            label,
            fill="#111111",
            font=tick_font,
        )
    for latitude in _temperature_axis_ticks(south, north, 0.02):
        y = bottom - (latitude - south) / (north - south) * (bottom - top)
        draw.line((left - 22, y, left, y), fill="#2b2b2b", width=7)
        label = f"{abs(latitude):.2f}°S"
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text(
            (left - (box[2] - box[0]) - 28, y - (box[3] - box[1]) / 2),
            label,
            fill="#111111",
            font=tick_font,
        )
    x_label = "Longitud (°W)"
    x_box = draw.textbbox((0, 0), x_label, font=axis_font)
    draw.text(
        ((left + right - (x_box[2] - x_box[0])) / 2, MAP_SIZE[1] - 78),
        x_label,
        fill="#050505",
        font=axis_font,
    )
    y_label = "Latitud (°S)"
    y_box = draw.textbbox((0, 0), y_label, font=axis_font)
    label_image = Image.new(
        "RGBA",
        (y_box[2] - y_box[0] + 16, y_box[3] - y_box[1] + 16),
        (255, 255, 255, 0),
    )
    ImageDraw.Draw(label_image).text((8, 8), y_label, fill="#050505", font=axis_font)
    rotated = label_image.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.alpha_composite(rotated, (8, round((top + bottom - rotated.height) / 2)))


def _draw_temperature_north_arrow(draw: ImageDraw.ImageDraw) -> None:
    left, top, _right, _bottom = TEMPERATURE_PLOT_BOX
    center_x = left + 190
    center_y = top + 190
    draw.ellipse(
        (center_x - 72, center_y - 55, center_x + 72, center_y + 85),
        outline=(5, 5, 5, 255),
        width=4,
    )
    draw.polygon(
        ((center_x, center_y - 88), (center_x - 55, center_y + 72), (center_x, center_y + 32)),
        fill=(255, 255, 255, 255),
        outline=(5, 5, 5, 255),
    )
    draw.polygon(
        ((center_x, center_y - 88), (center_x + 55, center_y + 72), (center_x, center_y + 32)),
        fill=(238, 238, 238, 255),
        outline=(5, 5, 5, 255),
    )
    font = _font(72)
    box = draw.textbbox((0, 0), "N", font=font)
    draw.text(
        (center_x - (box[2] - box[0]) / 2, top + 20),
        "N",
        fill="#ffffff",
        font=font,
    )


def _compose_temperature_design(
    map_image: Image.Image,
    bounds: tuple[float, float, float, float],
    report_date: date,
    start_time: str,
    end_time: str,
    minimum: float,
    maximum: float,
) -> Image.Image:
    canvas = Image.new("RGBA", MAP_SIZE, (255, 255, 255, 255))
    canvas.alpha_composite(
        map_image,
        (TEMPERATURE_PLOT_BOX[0], TEMPERATURE_PLOT_BOX[1]),
    )
    draw = ImageDraw.Draw(canvas, "RGBA")
    kind = "mínima" if maximum < 17 else "máxima"
    title = (
        f"Temperatura {kind} en Cuenca:\n"
        f"{SPANISH_WEEKDAYS[report_date.weekday()].capitalize()} "
        f"{report_date.day} de {SPANISH_MONTHS[report_date.month - 1]} {report_date.year}, "
        f"{start_time} - {end_time}"
    )
    title_font = _font(54, bold=True)
    title_box = draw.multiline_textbbox((0, 0), title, font=title_font, spacing=2, align="center")
    draw.multiline_text(
        ((MAP_SIZE[0] - (title_box[2] - title_box[0])) / 2, 16),
        title,
        fill="#050505",
        font=title_font,
        spacing=2,
        align="center",
    )
    _draw_temperature_axes(canvas, draw, bounds)
    _draw_temperature_north_arrow(draw)
    _draw_temperature_legend(canvas, minimum, maximum, _temperature_palette(maximum), kind)
    _draw_logo(canvas, TEMPERATURE_PLOT_BOX)
    draw.rectangle(TEMPERATURE_PLOT_BOX, outline=(5, 5, 5, 255), width=8)
    return canvas


def _draw_temperature_legend(
    canvas: Image.Image,
    minimum: float,
    maximum: float,
    palette: tuple[str, ...],
    kind: str,
) -> None:
    right, bottom = TEMPERATURE_PLOT_BOX[2], TEMPERATURE_PLOT_BOX[3]
    panel = (right - 390, bottom - 430, right, bottom)
    mica = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    mica_draw = ImageDraw.Draw(mica, "RGBA")
    mica_draw.rectangle(panel, fill=(248, 248, 248, 178))
    mica_crop = canvas.crop(panel).filter(ImageFilter.GaussianBlur(radius=2.2))
    mica.paste(mica_crop, panel[:2], mica_crop)
    tint = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(tint, "RGBA").rectangle(panel, fill=(248, 248, 248, 165))
    canvas.alpha_composite(mica)
    canvas.alpha_composite(tint)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.text(
        (panel[0] + 28, panel[1] + 18),
        f"Temperatura {kind} (°C)",
        fill="#111111",
        font=_font(30, bold=True),
    )
    bar = (panel[0] + 38, panel[1] + 82, panel[0] + 112, panel[3] - 28)
    for y in range(bar[1], bar[3]):
        ratio = 1 - (y - bar[1]) / max(1, bar[3] - bar[1] - 1)
        color = _gradient_color(ratio, 0, 1, palette)
        draw.line((bar[0], y, bar[2], y), fill=(*color, 255), width=1)
    draw.rectangle(bar, outline="#222222", width=2)
    for index in range(5):
        ratio = index / 4
        y = round(bar[3] - ratio * (bar[3] - bar[1]))
        value = minimum + ratio * (maximum - minimum)
        draw.line((bar[2], y, bar[2] + 12, y), fill="#222222", width=2)
        draw.text(
            (bar[2] + 28, y - 20),
            f"{value:.2f}",
            fill="#050505",
            font=_font(39, bold=True),
        )


def _job_copy(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return job.copy() if job else None


def _update_job(job_id: str, **values: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)

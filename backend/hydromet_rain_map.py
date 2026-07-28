from __future__ import annotations

import csv
import io
import json
import math
import threading
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont

from .config import APP_DATA_DIR

ASSET_DIR = Path(__file__).resolve().parent / "data" / "hydromet_rain_map"
BUFFER_PATH = ASSET_DIR / "buffer.geojson"
STATIONS_PATH = ASSET_DIR / "stations.csv"
LOGO_PATH = ASSET_DIR / "logo.png"
REPORT_ROOT = APP_DATA_DIR / "reports" / "hydromet-network"
TILE_CACHE = APP_DATA_DIR / "cache" / "hydromet-maptiles"
MAP_SIZE = (2200, 1450)
PLOT_BOX = (160, 110, 2140, 1320)
PLOT_SIZE = (PLOT_BOX[2] - PLOT_BOX[0], PLOT_BOX[3] - PLOT_BOX[1])
DEFAULT_SEARCH_RADIUS_KM = 10.0
DEFAULT_IDW_POWER = 2.0
DEFAULT_GRID_RESOLUTION_KM = 0.1
DEFAULT_ROUND_DIGITS = 2
RAIN_CATEGORIES = (
    (0.1, "#F3F4F6", "Sin lluvia [0 - 0.1]"),
    (2.0, "#AEDFF7", "Lluvia no significativa [0.1 a 2]"),
    (5.0, "#5CAFE6", "Lluvia ligera [2 a 5]"),
    (20.0, "#2B6FB2", "Lluvia moderada [5 a 20]"),
    (35.0, "#1A416E", "Lluvia intensa [20 a 35]"),
    (math.inf, "#0F203A", "Lluvia muy intensa ≥ 35"),
)
SPANISH_WEEKDAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
SPANISH_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True)
class Station:
    name: str
    longitude: float
    latitude: float
    elevation: float | None


_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def station_names() -> tuple[str, ...]:
    return tuple(station.name for station in _load_stations())


def create_rain_map_job(
    user_id: int,
    report_date: date,
    start_time: str,
    end_time: str,
    observations: dict[str, float | None],
    parameters: dict[str, Any] | None = None,
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
            "previewPath": None,
            "workbookPath": None,
            "error": None,
        }
    return job_id


def execute_rain_map_job(job_id: str) -> None:
    job = _job_copy(job_id)
    if not job:
        return
    _update_job(job_id, status="running", message="Generando mapa de lluvias")
    try:
        report_date = date.fromisoformat(job["reportDate"])
        image_path, workbook_path, preview_path = generate_rain_map(
            user_id=job["userId"],
            job_id=job_id,
            report_date=report_date,
            start_time=job["startTime"],
            end_time=job["endTime"],
            observations=job["observations"],
            **job["parameters"],
        )
        _update_job(
            job_id,
            status="completed",
            message="Mapa generado",
            imagePath=str(image_path),
            previewPath=str(preview_path),
            workbookPath=str(workbook_path),
        )
    except Exception as error:
        _update_job(
            job_id,
            status="failed",
            message="No se pudo generar el mapa",
            error=str(error),
        )


def rain_map_job(job_id: str, user_id: int) -> dict[str, Any] | None:
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


def rain_map_image(job_id: str, user_id: int) -> Path | None:
    job = _job_copy(job_id)
    if not job or job["userId"] != int(user_id) or job["status"] != "completed":
        return None
    image_path = Path(job["imagePath"])
    try:
        image_path.resolve().relative_to((REPORT_ROOT / str(user_id)).resolve())
    except ValueError:
        return None
    return image_path if image_path.is_file() else None


def rain_map_preview(job_id: str, user_id: int) -> Path | None:
    job = _job_copy(job_id)
    if not job or job["userId"] != int(user_id) or job["status"] != "completed":
        return None
    preview_path = Path(job["previewPath"])
    try:
        preview_path.resolve().relative_to((REPORT_ROOT / str(user_id)).resolve())
    except ValueError:
        return None
    return preview_path if preview_path.is_file() else None


def generate_rain_map(
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
    plot_logo: bool = True,
    plot_design: bool = True,
) -> tuple[Path, Path, Path]:
    stations = _load_stations()
    available = [
        (station, observations.get(station.name))
        for station in stations
        if observations.get(station.name) is not None
    ]
    if not available:
        raise ValueError("Ingresa al menos un valor de lluvia para generar el mapa.")

    job_root = REPORT_ROOT / str(user_id) / "jobs" / job_id
    output_dir = job_root / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = job_root / "BD_Obs.xlsx"
    image_path = output_dir / f"mapa_{report_date.isoformat()}.png"
    preview_path = output_dir / f"mapa_limpio_{report_date.isoformat()}.png"
    _write_observation_workbook(workbook_path, report_date, stations, observations)

    features = _load_buffer_features()
    source_bounds = _feature_bounds(features)
    bounds = _expand_bounds_to_aspect(source_bounds, PLOT_SIZE[0] / PLOT_SIZE[1])
    background = _basemap(bounds, PLOT_SIZE) if fetch_basemap else _fallback_basemap(PLOT_SIZE)
    grid_size = _grid_size(bounds, grid_resolution)
    rain_layer = _interpolated_rain_layer(
        bounds,
        features,
        available,
        grid_size,
        search_radius=search_radius,
        p=p,
        n_round=n_round,
    )
    rain_layer = rain_layer.resize(PLOT_SIZE, Image.Resampling.NEAREST)
    background = Image.alpha_composite(background.convert("RGBA"), rain_layer)
    _draw_boundaries(background, bounds, features)
    _draw_feature_labels(background, bounds, features)
    designed_map = _compose_map_design(
        background,
        bounds,
        report_date,
        start_time,
        end_time,
        plot_logo=plot_logo,
    )
    preview_map = _compose_clean_map(background, bounds, plot_logo=plot_logo)
    if not plot_design:
        designed_map = preview_map.copy()
    designed_map.convert("RGB").save(image_path, format="PNG", optimize=True)
    preview_map.convert("RGB").save(preview_path, format="PNG", optimize=True)
    return image_path, workbook_path, preview_path


def _job_copy(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return job.copy() if job else None


def _update_job(job_id: str, **values: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)


def _load_stations() -> list[Station]:
    stations: list[Station] = []
    with STATIONS_PATH.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            elevation = row["elevation"].strip()
            stations.append(
                Station(
                    name=row["station"],
                    longitude=float(row["longitude"]),
                    latitude=float(row["latitude"]),
                    elevation=float(elevation) if elevation else None,
                )
            )
    return stations


def _load_buffer_features() -> list[dict[str, Any]]:
    payload = json.loads(BUFFER_PATH.read_text(encoding="utf-8"))
    return payload["features"]


def _feature_rings(feature: dict[str, Any]) -> list[list[list[float]]]:
    geometry = feature["geometry"]
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        return [ring for polygon in geometry["coordinates"] for ring in polygon]
    return []


def _feature_bounds(features: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    points = [
        point
        for feature in features
        for ring in _feature_rings(feature)
        for point in ring
    ]
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def _expand_bounds_to_aspect(
    bounds: tuple[float, float, float, float],
    target_aspect: float,
) -> tuple[float, float, float, float]:
    west, south, east, north = bounds
    width = east - west
    height = north - south
    current_aspect = width / height
    if current_aspect < target_aspect:
        horizontal_padding = (height * target_aspect - width) / 2
        return west - horizontal_padding, south, east + horizontal_padding, north
    vertical_padding = (width / target_aspect - height) / 2
    return west, south - vertical_padding, east, north + vertical_padding


def _grid_size(
    bounds: tuple[float, float, float, float],
    resolution_km: float,
) -> tuple[int, int]:
    west, south, east, north = bounds
    center_latitude = (south + north) / 2
    width_km = (east - west) * 111.32 * math.cos(math.radians(center_latitude))
    height_km = (north - south) * 110.57
    width = max(120, min(1200, round(width_km / resolution_km)))
    height = max(90, min(900, round(height_km / resolution_km)))
    return width, height


def _write_observation_workbook(
    path: Path,
    report_date: date,
    stations: list[Station],
    observations: dict[str, float | None],
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Hoja1"
    sheet.append(("Date", datetime.combine(report_date, datetime.min.time())))
    for station in stations:
        sheet.append((station.name, observations.get(station.name)))
    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 16
    sheet["B1"].number_format = "m/d/yyyy"
    workbook.save(path)


def _world_pixel(longitude: float, latitude: float, zoom: int) -> tuple[float, float]:
    scale = 256 * (2**zoom)
    latitude = max(-85.05112878, min(85.05112878, latitude))
    sine = math.sin(math.radians(latitude))
    x = (longitude + 180.0) / 360.0 * scale
    y = (0.5 - math.log((1 + sine) / (1 - sine)) / (4 * math.pi)) * scale
    return x, y


def _basemap(bounds: tuple[float, float, float, float], size: tuple[int, int]) -> Image.Image:
    zoom = 13
    west, south, east, north = bounds
    left, top = _world_pixel(west, north, zoom)
    right, bottom = _world_pixel(east, south, zoom)
    tile_left, tile_top = math.floor(left / 256), math.floor(top / 256)
    tile_right, tile_bottom = math.floor(right / 256), math.floor(bottom / 256)
    mosaic = Image.new(
        "RGB",
        ((tile_right - tile_left + 1) * 256, (tile_bottom - tile_top + 1) * 256),
        "#dce3df",
    )
    coordinates = [
        (tile_x, tile_y)
        for tile_y in range(tile_top, tile_bottom + 1)
        for tile_x in range(tile_left, tile_right + 1)
    ]
    loaded = 0
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="rain-map-tile") as executor:
        futures = {
            executor.submit(_load_esri_tile, zoom, tile_x, tile_y): (tile_x, tile_y)
            for tile_x, tile_y in coordinates
        }
        for future in as_completed(futures):
            tile_x, tile_y = futures[future]
            tile = future.result()
            if tile:
                loaded += 1
                mosaic.paste(tile, ((tile_x - tile_left) * 256, (tile_y - tile_top) * 256))
    if not loaded:
        return _fallback_basemap(size)
    crop = (
        round(left - tile_left * 256),
        round(top - tile_top * 256),
        round(right - tile_left * 256),
        round(bottom - tile_top * 256),
    )
    return mosaic.crop(crop).resize(size, Image.Resampling.LANCZOS)


def _load_esri_tile(zoom: int, tile_x: int, tile_y: int) -> Image.Image | None:
    cache_path = TILE_CACHE / str(zoom) / str(tile_x) / f"{tile_y}.jpg"
    try:
        if cache_path.is_file():
            return Image.open(cache_path).convert("RGB")
        url = (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            f"World_Imagery/MapServer/tile/{zoom}/{tile_y}/{tile_x}"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "Agender/1.13"})
        with urllib.request.urlopen(request, timeout=8) as response:
            content = response.read(2 * 1024 * 1024)
        tile = Image.open(io.BytesIO(content)).convert("RGB")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tile.save(cache_path, format="JPEG", quality=90)
        return tile
    except (OSError, ValueError):
        return None


def _fallback_basemap(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, "#dce3df")
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 80):
        draw.line((x, 0, x, size[1]), fill="#cbd5d1", width=1)
    for y in range(0, size[1], 80):
        draw.line((0, y, size[0], y), fill="#cbd5d1", width=1)
    return image


def _map_point(
    longitude: float,
    latitude: float,
    bounds: tuple[float, float, float, float],
    size: tuple[int, int],
) -> tuple[int, int]:
    west, south, east, north = bounds
    x = (longitude - west) / (east - west) * (size[0] - 1)
    y = (north - latitude) / (north - south) * (size[1] - 1)
    return round(x), round(y)


def _polygon_mask(
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
    size: tuple[int, int],
) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for feature in features:
        rings = _feature_rings(feature)
        if not rings:
            continue
        draw.polygon([_map_point(*point, bounds, size) for point in rings[0]], fill=255)
        for hole in rings[1:]:
            draw.polygon([_map_point(*point, bounds, size) for point in hole], fill=0)
    return mask


def _cressman_value(
    longitude: float,
    latitude: float,
    observations: list[tuple[Station, float | None]],
    *,
    search_radius: float,
    p: float,
) -> float:
    cosine = math.cos(math.radians(latitude))
    weighted_sum = 0.0
    weight_total = 0.0
    idw_sum = 0.0
    idw_weight_total = 0.0
    radius_squared = search_radius**2
    for station, raw_value in observations:
        value = float(raw_value)
        dx = (longitude - station.longitude) * 111.32 * cosine
        dy = (latitude - station.latitude) * 110.57
        distance_squared = dx * dx + dy * dy
        if distance_squared <= 1e-12:
            return value
        distance = math.sqrt(distance_squared)
        idw_weight = 1 / (distance**p)
        idw_sum += idw_weight * value
        idw_weight_total += idw_weight
        if distance_squared < radius_squared:
            cressman_weight = (
                (radius_squared - distance_squared)
                / (radius_squared + distance_squared)
            )
            weight = cressman_weight * idw_weight
            weighted_sum += weight * value
            weight_total += weight
    return weighted_sum / weight_total if weight_total else idw_sum / idw_weight_total


def _rain_color(value: float) -> str:
    for maximum, color, _label in RAIN_CATEGORIES:
        if value < maximum:
            return color
    return RAIN_CATEGORIES[-1][1]


def _interpolated_rain_layer(
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
    observations: list[tuple[Station, float | None]],
    size: tuple[int, int],
    *,
    search_radius: float,
    p: float,
    n_round: int,
) -> Image.Image:
    west, south, east, north = bounds
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = layer.load()
    for y in range(size[1]):
        latitude = north - (y / max(1, size[1] - 1)) * (north - south)
        for x in range(size[0]):
            longitude = west + (x / max(1, size[0] - 1)) * (east - west)
            value = round(
                _cressman_value(
                    longitude,
                    latitude,
                    observations,
                    search_radius=search_radius,
                    p=p,
                ),
                n_round,
            )
            red, green, blue = ImageColor.getrgb(_rain_color(value))
            pixels[x, y] = red, green, blue, 145
    mask = _polygon_mask(bounds, features, size)
    alpha = ImageChops.multiply(layer.getchannel("A"), mask)
    layer.putalpha(alpha)
    return layer


def _draw_boundaries(
    image: Image.Image,
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for feature in features:
        for ring in _feature_rings(feature):
            points = [_map_point(*point, bounds, image.size) for point in ring]
            if len(points) > 1:
                _draw_dashed_line(
                    draw,
                    [*points, points[0]],
                    fill=(5, 5, 5, 245),
                    width=5,
                    dash=20,
                    gap=15,
                )

    for feature in features:
        if feature.get("properties", {}).get("name") != "CUENCA":
            continue
        for ring in _feature_rings(feature):
            points = [_map_point(*point, bounds, image.size) for point in ring]
            if len(points) > 1:
                draw.line((*points, points[0]), fill=(5, 5, 5, 255), width=7, joint="curve")

    union_mask = _polygon_mask(bounds, features, image.size)
    outside = union_mask.filter(ImageFilter.MaxFilter(9))
    inside = union_mask.filter(ImageFilter.MinFilter(9))
    outer_edge = ImageChops.subtract(outside, inside)
    outline = Image.new("RGBA", image.size, (0, 0, 0, 0))
    outline.putalpha(outer_edge)
    image.alpha_composite(outline)


def _draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    fill: tuple[int, int, int, int],
    width: int,
    dash: int,
    gap: int,
) -> None:
    pattern = dash + gap
    distance_offset = 0.0
    for start, end in pairwise(points):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        cursor = -distance_offset
        while cursor < length:
            segment_start = max(0.0, cursor)
            segment_end = min(length, cursor + dash)
            if segment_end > segment_start:
                ratio_start = segment_start / length
                ratio_end = segment_end / length
                draw.line(
                    (
                        start[0] + dx * ratio_start,
                        start[1] + dy * ratio_start,
                        start[0] + dx * ratio_end,
                        start[1] + dy * ratio_end,
                    ),
                    fill=fill,
                    width=width,
                )
            cursor += pattern
        distance_offset = (distance_offset + length) % pattern


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    area_twice = 0.0
    longitude_total = 0.0
    latitude_total = 0.0
    for start, end in zip(ring, [*ring[1:], ring[0]], strict=False):
        cross = start[0] * end[1] - end[0] * start[1]
        area_twice += cross
        longitude_total += (start[0] + end[0]) * cross
        latitude_total += (start[1] + end[1]) * cross
    if abs(area_twice) < 1e-12:
        return (
            sum(point[0] for point in ring) / len(ring),
            sum(point[1] for point in ring) / len(ring),
        )
    return longitude_total / (3 * area_twice), latitude_total / (3 * area_twice)


def _draw_feature_labels(
    image: Image.Image,
    bounds: tuple[float, float, float, float],
    features: list[dict[str, Any]],
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for feature in features:
        rings = _feature_rings(feature)
        name = feature.get("properties", {}).get("name", "")
        if not rings or not name:
            continue
        longitude, latitude = _ring_centroid(rings[0])
        x, y = _map_point(longitude, latitude, bounds, image.size)
        is_city = name == "CUENCA"
        font = _font(43 if is_city else 27, bold=True)
        box = draw.textbbox((0, 0), name, font=font)
        draw.text(
            (x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2),
            name,
            fill=(255, 255, 255, 255),
            font=font,
            stroke_width=2,
            stroke_fill=(45, 45, 45, 150),
        )


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    filenames = ("C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/arialbd.ttf") if bold else (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    )
    for filename in filenames:
        try:
            return ImageFont.truetype(filename, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _compose_map_design(
    map_image: Image.Image,
    bounds: tuple[float, float, float, float],
    report_date: date,
    start_time: str,
    end_time: str,
    *,
    plot_logo: bool,
) -> Image.Image:
    canvas = Image.new("RGBA", MAP_SIZE, (255, 255, 255, 255))
    canvas.alpha_composite(map_image, (PLOT_BOX[0], PLOT_BOX[1]))
    draw = ImageDraw.Draw(canvas, "RGBA")
    title = (
        "Lluvia acumulada:\n"
        f"{SPANISH_WEEKDAYS[report_date.weekday()].capitalize()} "
        f"{report_date.day} de {SPANISH_MONTHS[report_date.month - 1]} {report_date.year}, "
        f"{start_time} - {end_time}"
    )
    title_font = _font(43, bold=True)
    title_box = draw.multiline_textbbox(
        (0, 0),
        title,
        font=title_font,
        spacing=2,
        align="center",
    )
    title_width = title_box[2] - title_box[0]
    draw.multiline_text(
        ((MAP_SIZE[0] - title_width) / 2, 8),
        title,
        fill="#050505",
        font=title_font,
        spacing=2,
        align="center",
    )
    _draw_axes(canvas, draw, bounds)
    _draw_north_arrow(draw, PLOT_BOX)
    _draw_scale_bar(draw, bounds, PLOT_BOX)
    _draw_legend(canvas, draw, PLOT_BOX)
    if plot_logo:
        _draw_logo(canvas, PLOT_BOX)
    draw.rectangle(PLOT_BOX, outline=(5, 5, 5, 255), width=5)
    return canvas


def _compose_clean_map(
    map_image: Image.Image,
    bounds: tuple[float, float, float, float],
    *,
    plot_logo: bool,
) -> Image.Image:
    canvas = map_image.copy()
    draw = ImageDraw.Draw(canvas, "RGBA")
    box = (0, 0, canvas.width - 1, canvas.height - 1)
    _draw_north_arrow(draw, box)
    _draw_scale_bar(draw, bounds, box)
    _draw_legend(canvas, draw, box)
    if plot_logo:
        _draw_logo(canvas, box)
    draw.rectangle(box, outline=(5, 5, 5, 255), width=5)
    return canvas


def _axis_ticks(start: float, end: float, step: float) -> list[float]:
    first = math.ceil((start - 1e-9) / step) * step
    values = []
    value = first
    while value <= end + 1e-9:
        values.append(round(value, 10))
        value += step
    return values


def _draw_axes(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    bounds: tuple[float, float, float, float],
) -> None:
    west, south, east, north = bounds
    left, top, right, bottom = PLOT_BOX
    label_font = _font(29)
    axis_font = _font(34)
    for longitude in _axis_ticks(west, east, 0.1):
        x = left + (longitude - west) / (east - west) * (right - left)
        draw.line((x, bottom, x, bottom + 12), fill="#222222", width=3)
        label = f"{abs(longitude):.1f}°W"
        box = draw.textbbox((0, 0), label, font=label_font)
        draw.text((x - (box[2] - box[0]) / 2, bottom + 15), label, fill="#555555", font=label_font)
    for latitude in _axis_ticks(south, north, 0.05):
        y = bottom - (latitude - south) / (north - south) * (bottom - top)
        draw.line((left - 12, y, left, y), fill="#222222", width=3)
        label = f"{abs(latitude):.2f}°S"
        box = draw.textbbox((0, 0), label, font=label_font)
        draw.text(
            (left - (box[2] - box[0]) - 18, y - (box[3] - box[1]) / 2),
            label,
            fill="#555555",
            font=label_font,
        )

    x_label = "Longitud (°W)"
    x_box = draw.textbbox((0, 0), x_label, font=axis_font)
    draw.text(
        ((left + right - (x_box[2] - x_box[0])) / 2, MAP_SIZE[1] - 48),
        x_label,
        fill="#111111",
        font=axis_font,
    )
    y_label = "Latitud (°S)"
    y_box = draw.textbbox((0, 0), y_label, font=axis_font)
    label_image = Image.new(
        "RGBA",
        (y_box[2] - y_box[0] + 12, y_box[3] - y_box[1] + 12),
        (255, 255, 255, 0),
    )
    ImageDraw.Draw(label_image).text((6, 6), y_label, fill="#111111", font=axis_font)
    rotated = label_image.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.alpha_composite(
        rotated,
        (24, round((top + bottom - rotated.height) / 2)),
    )


def _draw_north_arrow(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
) -> None:
    left, top, _right, _bottom = box
    center_x = left + 125
    center_y = top + 125
    draw.ellipse(
        (center_x - 50, center_y - 35, center_x + 50, center_y + 65),
        outline=(10, 10, 10, 255),
        width=3,
    )
    draw.polygon(
        (
            (center_x, center_y - 55),
            (center_x - 35, center_y + 48),
            (center_x, center_y + 23),
        ),
        fill=(255, 255, 255, 255),
        outline=(10, 10, 10, 255),
    )
    draw.polygon(
        (
            (center_x, center_y - 55),
            (center_x + 35, center_y + 48),
            (center_x, center_y + 23),
        ),
        fill=(225, 225, 225, 255),
        outline=(10, 10, 10, 255),
    )
    north = "N"
    font = _font(45)
    box = draw.textbbox((0, 0), north, font=font)
    draw.text((center_x - (box[2] - box[0]) / 2, top + 8), north, fill="#ffffff", font=font)


def _draw_scale_bar(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[float, float, float, float],
    box: tuple[int, int, int, int],
) -> None:
    west, _south, east, _north = bounds
    left, _top, right, bottom = box
    center_latitude = (bounds[1] + bounds[3]) / 2
    ten_km_degrees = 10 / (111.32 * math.cos(math.radians(center_latitude)))
    scale_width = round(ten_km_degrees / (east - west) * (right - left))
    scale_width = max(220, min(360, scale_width))
    scale_left = left + 20
    scale_top = bottom - 42
    segment_width = scale_width / 4
    for index in range(4):
        segment_left = round(scale_left + index * segment_width)
        segment_right = round(scale_left + (index + 1) * segment_width)
        fill = "#050505" if index % 2 == 0 else "#ffffff"
        draw.rectangle(
            (segment_left, scale_top, segment_right, scale_top + 22),
            fill=fill,
            outline="#ffffff",
            width=2,
        )
    draw.rectangle(
        (scale_left, scale_top, scale_left + scale_width, scale_top + 22),
        outline="#ffffff",
        width=3,
    )
    draw.text(
        (scale_left + scale_width + 12, scale_top - 10),
        "10 km",
        fill="#ffffff",
        font=_font(30),
        stroke_width=2,
        stroke_fill="#222222",
    )


def _draw_legend(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
) -> None:
    _left, _top, right, bottom = box
    panel_width = 575
    row_height = 36
    panel_height = 62 + row_height * len(RAIN_CATEGORIES)
    panel_left = right - panel_width
    panel_top = bottom - panel_height
    panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rectangle(
        (panel_left, panel_top, right, bottom),
        fill=(255, 255, 255, 205),
    )
    canvas.alpha_composite(panel)
    draw.text(
        (panel_left + 112, panel_top + 5),
        "Lluvia diaria (mm)",
        fill="#111111",
        font=_font(31, bold=True),
    )
    for index, (_maximum, color, label) in enumerate(RAIN_CATEGORIES):
        y = panel_top + 55 + index * row_height
        draw.rectangle((panel_left, y, panel_left + 48, y + row_height), fill=color)
        draw.text((panel_left + 66, y - 1), label, fill="#111111", font=_font(27))


def _draw_logo(canvas: Image.Image, box: tuple[int, int, int, int]) -> None:
    if LOGO_PATH.is_file():
        with Image.open(LOGO_PATH) as logo_source:
            logo = logo_source.convert("RGBA")
            maximum_width, maximum_height = 500, 105
            logo.thumbnail((maximum_width, maximum_height), Image.Resampling.LANCZOS)
            _left, top, right, _bottom = box
            panel = (
                right - 540,
                top,
                right,
                top + 125,
            )
            background = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(background).rectangle(panel, fill=(255, 255, 255, 190))
            canvas.alpha_composite(background)
            canvas.alpha_composite(
                logo,
                (right - logo.width - 18, top + round((125 - logo.height) / 2)),
            )

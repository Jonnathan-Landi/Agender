from __future__ import annotations

import threading
import sqlite3
import struct
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from io import BytesIO
from functools import lru_cache
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageDraw

from .config import CACHE_DIR

BASE_URL = "https://geo.etapa.net.ec/visorradar/img"
SCOPES_KM = (100, 60, 20)
INTERVAL_MINUTES = 5
WINDOW_MINUTES = 240
TIMEOUT_SECONDS = 15
ECUADOR_TZ = timezone(timedelta(hours=-5))
CACHE_ROOT = CACHE_DIR / "radar-caxx"
SOURCE_ROOT = CACHE_ROOT / "source"
FRAME_ROOT = CACHE_ROOT / "frames"
AREA_SOURCE_ROOT = Path(__file__).resolve().parent / "data" / "radar_caxx"
COMPOSITION_VERSION = "4"
_refresh_lock = threading.Lock()
_last_refresh_slot: datetime | None = None


def rounded_local_time(now: datetime | None = None) -> datetime:
    current = now.astimezone(ECUADOR_TZ) if now else datetime.now(ECUADOR_TZ)
    return current.replace(
        minute=(current.minute // INTERVAL_MINUTES) * INTERVAL_MINUTES,
        second=0,
        microsecond=0,
    )


def window_times(now: datetime | None = None) -> list[tuple[datetime, datetime]]:
    end = rounded_local_time(now)
    start = end - timedelta(minutes=WINDOW_MINUTES)
    slots = WINDOW_MINUTES // INTERVAL_MINUTES
    return [
        (start + timedelta(minutes=index * INTERVAL_MINUTES),
         (start + timedelta(minutes=index * INTERVAL_MINUTES)).astimezone(UTC))
        for index in range(slots + 1)
    ]


def source_url(scope_km: int, utc_time: datetime) -> tuple[str, str]:
    filename = utc_time.strftime("%Y%m%d%H%M") + "0000dBuZ.ppi_top.gif"
    return f"{BASE_URL}/{scope_km}km/{utc_time:%Y-%m-%d}/{filename}", filename


def _source_path(scope_km: int, filename: str) -> Path:
    return SOURCE_ROOT / f"{scope_km}km" / filename


def _download_source(scope_km: int, utc_time: datetime) -> Path | None:
    url, filename = source_url(scope_km, utc_time)
    destination = _source_path(scope_km, filename)
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    try:
        response = requests.get(
            url,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": "Agender Radar-CAXX/1.0"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if not response.content.startswith((b"GIF87a", b"GIF89a")):
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".gif.tmp")
        temporary.write_bytes(response.content)
        temporary.replace(destination)
        return destination
    except (OSError, requests.RequestException):
        return None


def _transparent_radar_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        source.seek(0)
        return source.convert("RGBA")


def compose_frame(utc_time: datetime) -> Path | None:
    timestamp = utc_time.strftime("%Y%m%d%H%M")
    output = FRAME_ROOT / f"{timestamp}.png"
    sources = []
    for scope_km in SCOPES_KM:
        _, filename = source_url(scope_km, utc_time)
        path = _source_path(scope_km, filename)
        if path.is_file():
            sources.append((scope_km, path))
    if len(sources) != len(SCOPES_KM):
        return None
    newest_source = max(path.stat().st_mtime for _, path in sources)
    if output.is_file() and output.stat().st_mtime >= newest_source:
        return output

    # 2000 px preserves the native ~400 px detail of the 20 km product
    # while sharing the same 200 x 200 km UTM canvas with every scope.
    canvas_size = 2000
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    inner_radius_by_scope = {100: 60, 60: 20, 20: 0}
    for scope_km, path in sources:
        layer = _transparent_radar_image(path)
        target_size = round(canvas_size * scope_km / 100)
        layer = layer.resize((target_size, target_size), Image.Resampling.BILINEAR)
        offset = (canvas_size - target_size) // 2
        positioned = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        positioned.alpha_composite(layer, (offset, offset))
        annulus = Image.new("L", (canvas_size, canvas_size), 0)
        drawing = ImageDraw.Draw(annulus)
        drawing.ellipse((offset, offset, offset + target_size, offset + target_size), fill=255)
        inner_scope = inner_radius_by_scope[scope_km]
        if inner_scope:
            inner_size = round(canvas_size * inner_scope / 100)
            inner_offset = (canvas_size - inner_size) // 2
            drawing.ellipse(
                (inner_offset, inner_offset, inner_offset + inner_size, inner_offset + inner_size),
                fill=0,
            )
        positioned.putalpha(ImageChops.multiply(positioned.getchannel("A"), annulus))
        canvas.alpha_composite(positioned)
    FRAME_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".png.tmp")
    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    temporary.write_bytes(buffer.getvalue())
    temporary.replace(output)
    return output


def _gpkg_geometry(blob: bytes) -> list[list[list[tuple[float, float]]]]:
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    position = 8 + envelope_sizes[(blob[3] >> 1) & 0b111]

    def read(offset: int):
        byte_order = "<" if blob[offset] == 1 else ">"
        geometry_type = struct.unpack_from(f"{byte_order}I", blob, offset + 1)[0] % 1000
        offset += 5
        if geometry_type == 3:
            ring_count = struct.unpack_from(f"{byte_order}I", blob, offset)[0]
            offset += 4
            rings = []
            for _ in range(ring_count):
                point_count = struct.unpack_from(f"{byte_order}I", blob, offset)[0]
                offset += 4
                ring = []
                for _ in range(point_count):
                    ring.append(struct.unpack_from(f"{byte_order}dd", blob, offset))
                    offset += 16
                rings.append(ring)
            return [rings], offset
        if geometry_type == 6:
            polygon_count = struct.unpack_from(f"{byte_order}I", blob, offset)[0]
            offset += 4
            polygons = []
            for _ in range(polygon_count):
                nested, offset = read(offset)
                polygons.extend(nested)
            return polygons, offset
        raise ValueError("Geometría territorial no compatible")

    return read(position)[0]


@lru_cache(maxsize=8)
def _area_mask(area: str, canvas_size: int) -> Image.Image:
    sources = {
        "subcuencas": ("Subcuencas.gpkg", "sub_paute"),
        "urbana": ("ZonaUrbana.gpkg", "cuenca"),
    }
    if area not in sources:
        raise ValueError("Área de vigilancia no válida")
    filename, table = sources[area]
    with sqlite3.connect(AREA_SOURCE_ROOT / filename) as connection:
        geometries = connection.execute(f'SELECT geom FROM "{table}"').fetchall()
    radar_x, radar_y = 694_951.002, 9_694_792.553

    def pixel(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (
            (x - (radar_x - 100_000)) / 200_000 * canvas_size,
            ((radar_y + 100_000) - y) / 200_000 * canvas_size,
        )

    mask = Image.new("L", (canvas_size, canvas_size), 0)
    drawing = ImageDraw.Draw(mask)
    for (blob,) in geometries:
        for polygon in _gpkg_geometry(blob):
            if polygon:
                drawing.polygon([pixel(point) for point in polygon[0]], fill=255)
                for hole in polygon[1:]:
                    drawing.polygon([pixel(point) for point in hole], fill=0)
    return mask


def resolve_area_frame(frame_id: str, area: str = "cuenca") -> Path:
    source = resolve_frame(frame_id)
    if area == "cuenca":
        return source
    if area not in {"subcuencas", "urbana"}:
        raise ValueError("Área de vigilancia no válida")
    output = FRAME_ROOT / "areas" / area / source.name
    if output.is_file() and output.stat().st_mtime >= source.stat().st_mtime:
        return output
    with Image.open(source) as image:
        product = image.convert("RGBA")
    mask = _area_mask(area, product.width)
    product.putalpha(ImageChops.multiply(product.getchannel("A"), mask))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".png.tmp")
    product.save(temporary, format="PNG", optimize=True)
    temporary.replace(output)
    return output


def _cleanup(valid_timestamps: set[str]) -> None:
    for root, suffix in ((SOURCE_ROOT, ".gif"), (FRAME_ROOT, ".png")):
        if not root.is_dir():
            continue
        for path in root.rglob(f"*{suffix}"):
            if path.stem[:12] not in valid_timestamps:
                try:
                    path.unlink()
                except OSError:
                    pass


def _ensure_composition_version() -> None:
    marker = CACHE_ROOT / ".composition-version"
    try:
        current = marker.read_text(encoding="utf-8")
    except OSError:
        current = ""
    if current == COMPOSITION_VERSION:
        return
    if FRAME_ROOT.is_dir():
        for path in FRAME_ROOT.rglob("*.png"):
            try:
                path.unlink()
            except OSError:
                pass
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    marker.write_text(COMPOSITION_VERSION, encoding="utf-8")


def refresh_cache(now: datetime | None = None, force: bool = False) -> list[dict[str, str]]:
    global _last_refresh_slot
    slots = window_times(now)
    current_slot = slots[-1][0]
    with _refresh_lock:
        _ensure_composition_version()
        if not force and _last_refresh_slot == current_slot:
            return frame_catalog()
        valid_timestamps = {utc.strftime("%Y%m%d%H%M") for _, utc in slots}
        _cleanup(valid_timestamps)
        jobs = [(scope, utc) for _, utc in slots for scope in SCOPES_KM]
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda job: _download_source(*job), jobs))
        for _, utc in slots:
            compose_frame(utc)
        _cleanup(valid_timestamps)
        latest_id = slots[-1][1].strftime("%Y%m%d%H%M")
        if (FRAME_ROOT / f"{latest_id}.png").is_file():
            _last_refresh_slot = current_slot
        return frame_catalog()


def frame_catalog() -> list[dict[str, str]]:
    if not FRAME_ROOT.is_dir():
        return []
    frames = []
    for path in sorted(FRAME_ROOT.glob("????????????.png")):
        try:
            utc_time = datetime.strptime(path.stem, "%Y%m%d%H%M").replace(tzinfo=UTC)
        except ValueError:
            continue
        local_time = utc_time.astimezone(ECUADOR_TZ)
        frames.append(
            {
                "id": path.stem,
                "localTime": local_time.isoformat(),
                "label": local_time.strftime("%H:%M"),
                "imageUrl": f"/api/radar-caxx/frames/{path.stem}.png",
            }
        )
    return frames


def resolve_frame(frame_id: str) -> Path:
    if len(frame_id) != 12 or not frame_id.isdigit():
        raise ValueError("Fotograma no válido")
    path = FRAME_ROOT / f"{frame_id}.png"
    if not path.is_file():
        raise FileNotFoundError(frame_id)
    return path

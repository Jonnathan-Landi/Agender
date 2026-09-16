from __future__ import annotations

import json
import logging
import re
import threading
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import requests

from .config import CACHE_DIR

BUCKET_URL = "https://noaa-goes19.s3.amazonaws.com"
PRODUCT = "ABI-L2-CMIPF"
CHANNEL = "C13_G19"
INTERVAL = timedelta(minutes=10)
WINDOW = timedelta(hours=3)
LOCAL_TZ = timezone(timedelta(hours=-5))
CACHE_ROOT = CACHE_DIR / "goes19"
RAW_ROOT = CACHE_ROOT / "raw"
PROCESSED_ROOT = CACHE_ROOT / "processed"
FRAME_ROOT = CACHE_ROOT / "frames"
STATE_PATH = CACHE_ROOT / "state.json"
VERSION_PATH = CACHE_ROOT / ".render-version"
OWNER_PATH = CACHE_ROOT / ".worker-owner"
RENDER_VERSION = 6
GOES_VIEW_CENTER = (697_950, 9_682_884)
# GOESHub expands Azuay's 149,271.6 m UTM width by 400 km on each side,
# then applies its render zoom of 1.7.
GOES_VIEW_SIDE = (800_000 + 149_271.6) / 1.7
OUTPUT_SIZE = 2000
LOGO_PATH = Path(__file__).resolve().parent / "data" / "goes19" / "logo.png"
GEODATA_PATH = Path(__file__).resolve().parent.parent / "frontend" / "js" / "data" / "radar-caxx-geodata.js"
KEY_STAMP = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})\d?_")
FRAME_ID = re.compile(r"^\d{12}$")
_lock = threading.Lock()
_hour_listing: dict[str, tuple[datetime, list[str]]] = {}
_logger = logging.getLogger(__name__)
_instance_token = f"{uuid.uuid4().hex}"


def claim_cache_ownership() -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = OWNER_PATH.with_suffix(f".{_instance_token}.part")
    temporary.write_text(_instance_token, encoding="utf-8")
    temporary.replace(OWNER_PATH)


def owns_cache() -> bool:
    try:
        return OWNER_PATH.read_text(encoding="utf-8").strip() == _instance_token
    except OSError:
        return False


def release_cache_ownership() -> None:
    if owns_cache():
        OWNER_PATH.unlink(missing_ok=True)


def floor_slot(now: datetime | None = None) -> datetime:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    return current.replace(minute=current.minute // 10 * 10, second=0, microsecond=0)


def window_slots(now: datetime | None = None) -> list[datetime]:
    end = floor_slot(now)
    return [end - WINDOW + index * INTERVAL for index in range(19)]


def slot_id(slot: datetime) -> str:
    return slot.astimezone(UTC).strftime("%Y%m%d%H%M")


def next_refresh_time(now: datetime, current_ready: bool) -> datetime:
    current = now.astimezone(UTC)
    if current_ready:
        return floor_slot(current) + INTERVAL
    return current.replace(second=0, microsecond=0) + timedelta(minutes=1)


def key_slot(key: str) -> datetime | None:
    match = KEY_STAMP.search(key)
    if not match or CHANNEL not in key or not key.endswith(".nc"):
        return None
    year, day, hour, minute, _second = map(int, match.groups())
    try:
        start = datetime(year, 1, 1, tzinfo=UTC) + timedelta(
            days=day - 1, hours=hour, minutes=minute
        )
        return floor_slot(start)
    except ValueError:
        return None


def _list_hour(hour: datetime, now: datetime) -> list[str]:
    prefix = f"{PRODUCT}/{hour:%Y}/{hour:%j}/{hour:%H}/"
    cached = _hour_listing.get(prefix)
    if cached and now - cached[0] < timedelta(minutes=1):
        return cached[1]
    keys: list[str] = []
    token: str | None = None
    while True:
        params: dict[str, str | int] = {
            "list-type": 2, "prefix": prefix, "max-keys": 1000
        }
        if token:
            params["continuation-token"] = token
        response = requests.get(BUCKET_URL + "/", params=params, timeout=25)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        for contents in root.findall("{*}Contents"):
            key = contents.findtext("{*}Key")
            if key and CHANNEL in key and key.endswith(".nc"):
                keys.append(key)
        truncated = root.findtext("{*}IsTruncated", "false").lower() == "true"
        token = root.findtext("{*}NextContinuationToken")
        if not truncated or not token:
            break
    _hour_listing[prefix] = (now, keys)
    return keys


def _download(key: str, destination: Path) -> bool:
    if destination.is_file() and destination.stat().st_size >= 50_000:
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".nc.part")
    try:
        with requests.get(f"{BUCKET_URL}/{key}", stream=True, timeout=(20, 120)) as response:
            if response.status_code == 404:
                return False
            response.raise_for_status()
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        stream.write(chunk)
        if temporary.stat().st_size < 50_000:
            return False
        temporary.replace(destination)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _palette(values):
    import numpy as np

    # Keep GOESHub's piecewise C13 ramps and their deliberate discontinuities
    # at -70, -55, -35 and -10 °C. A single gradient makes land brown.
    segments = (
        (-90, -85, (95, 59, 150), (133, 76, 157)),
        (-85, -80, (133, 76, 157), (189, 31, 36)),
        (-80, -70, (189, 31, 36), (243, 131, 117)),
        (-70, -60, (35, 63, 151), (56, 126, 193)),
        (-60, -55, (56, 126, 193), (49, 185, 235)),
        (-55, -50, (24, 119, 60), (89, 185, 72)),
        (-50, -45, (89, 185, 72), (241, 237, 118)),
        (-45, -40, (241, 237, 118), (213, 213, 40)),
        (-40, -35, (213, 213, 40), (239, 196, 88)),
        (-35, -30, (239, 196, 88), (240, 166, 39)),
        (-30, -20, (240, 166, 39), (169, 85, 37)),
        (-20, -10, (169, 85, 37), (101, 85, 70)),
        (-10, 50, (128, 127, 127), (2, 3, 3)),
    )
    midpoints = np.floor(np.clip(values, -90, 49.999)) + 0.5
    rgb = np.zeros((*values.shape, 3), dtype=np.uint8)
    for lower, upper, first, last in segments:
        mask = np.isfinite(values) & (midpoints >= lower) & (midpoints < upper)
        if not np.any(mask):
            continue
        fraction = (midpoints[mask] - lower) / (upper - lower)
        rgb[mask] = np.rint(
            np.asarray(first) + fraction[:, None] * (np.asarray(last) - np.asarray(first))
        ).astype(np.uint8)
    return rgb


@lru_cache(maxsize=1)
def _geodata() -> dict:
    source = GEODATA_PATH.read_text(encoding="utf-8")
    return json.loads(source.split("=", 1)[1].strip().rstrip(";"))


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    names = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/seguisb.ttf"] if bold else [
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_frame(temperature, slot: datetime, destination: Path) -> None:
    import numpy as np
    from PIL import Image, ImageDraw

    side = GOES_VIEW_SIDE
    west = GOES_VIEW_CENTER[0] - side / 2
    north = GOES_VIEW_CENTER[1] + side / 2

    def pixels(ring):
        return [((x - west) / side * OUTPUT_SIZE, (north - y) / side * OUTPUT_SIZE) for x, y in ring]

    raster = Image.fromarray(_palette(temperature), "RGB")
    canvas = raster.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.Resampling.NEAREST).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    geography = _geodata()
    for polygon in geography["country"]:
        for ring in polygon:
            draw.line(pixels(ring), fill="white", width=5, joint="curve")
    cuenca = geography["cuenca"][0]
    for polygon in cuenca["polygons"]:
        for ring in polygon:
            points = pixels(ring)
            draw.line(points, fill="white", width=12, joint="curve")
            draw.line(points, fill="black", width=7, joint="curve")
    label_x = (GOES_VIEW_CENTER[0] - west) / side * OUTPUT_SIZE
    label_y = (north - GOES_VIEW_CENTER[1]) / side * OUTPUT_SIZE
    draw.text((label_x, label_y + 15), "CUENCA", font=_font(42, bold=True),
              anchor="mm", fill="white", stroke_width=5, stroke_fill="black")

    # The black strip, logo, title and Ecuador time are part of every frame in
    # GOESHub, rather than separate application furniture.
    header_height = 180
    draw.rectangle((0, 0, OUTPUT_SIZE, header_height), fill="black")
    if LOGO_PATH.is_file():
        with Image.open(LOGO_PATH) as source:
            logo = source.convert("RGBA")
            logo.thumbnail((530, 145), Image.Resampling.LANCZOS)
            canvas.alpha_composite(logo, (18, (header_height - logo.height) // 2))
    draw = ImageDraw.Draw(canvas)
    title_font = _font(45, bold=True)
    draw.text((1000, 65), "Nubosidad con potencial de", font=title_font,
              anchor="mm", fill="white")
    draw.text((1000, 120), "tormentas (GOES-19)", font=title_font,
              anchor="mm", fill="white")
    local = slot.astimezone(LOCAL_TZ)
    draw.text((1980, 92), local.strftime("%Y-%m-%d %H:%M  [Hora Ecuador]"),
              font=_font(34, bold=True), anchor="rm", fill="white")

    legend = (20, 1730, 680, 1980)
    draw.rounded_rectangle(legend, radius=18, fill=(230, 233, 237, 245))
    draw.text((58, 1762), "Banda 13:", font=_font(31, bold=True), fill="black")
    draw.text((58, 1815), "Canal 13 (10.3 µm) Ventana IR (limpia)",
              font=_font(25), fill="black")
    bar_left, bar_right, bar_top, bar_bottom = 78, 620, 1860, 1900
    values = -90 + np.arange(bar_right - bar_left) / (bar_right - bar_left) * 140
    colors = _palette(values)
    for index, x in enumerate(range(bar_left, bar_right)):
        color = tuple(int(number) for number in colors[index])
        draw.line((x, bar_top, x, bar_bottom), fill=color)
    draw.polygon(((55, 1880), (78, 1856), (78, 1904)), fill="black")
    draw.polygon(((643, 1880), (620, 1856), (620, 1904)), fill="black")
    ticks = (-90, -75, -60, -45, -30, -15, 0, 15, 30, 45)
    for value in ticks:
        x = bar_left + (value + 90) / 140 * (bar_right - bar_left)
        draw.line((x, 1900, x, 1920), fill="black", width=2)
        draw.text((x, 1940), str(value), font=_font(22, bold=True), anchor="mm", fill="black")

    temporary_frame = destination.with_suffix(".png.part")
    canvas.convert("RGB").save(temporary_frame, format="PNG", optimize=True)
    temporary_frame.replace(destination)


def _process(source: Path, processed: Path, frame: Path) -> None:
    import netCDF4
    import numpy as np
    from pyproj import CRS, Transformer

    # GOESHub renders its 800 km UTM raster at zoom 1.7 about Cuenca.
    # The 0.35/0.65 vertical split plus 0.15 pan resolves to a centered view.
    width = height = round(GOES_VIEW_SIDE / 2_000)
    half = GOES_VIEW_SIDE / 2
    resolution = GOES_VIEW_SIDE / width
    x_utm = GOES_VIEW_CENTER[0] - half + (np.arange(width) + 0.5) * resolution
    y_utm = GOES_VIEW_CENTER[1] + half - (np.arange(height) + 0.5) * resolution
    xx, yy = np.meshgrid(x_utm, y_utm)
    with netCDF4.Dataset(source) as dataset:
        projection = dataset.variables["goes_imager_projection"]
        perspective = float(projection.perspective_point_height)
        geos = CRS.from_proj4(
            f"+proj=geos +h={perspective} "
            f"+lon_0={projection.longitude_of_projection_origin} "
            f"+sweep={projection.sweep_angle_axis} +ellps=GRS80 +units=m"
        )
        geo_x, geo_y = Transformer.from_crs("EPSG:32717", geos, always_xy=True).transform(xx, yy)
        scan_x = np.asarray(dataset.variables["x"][:], dtype=np.float64) * perspective
        scan_y = np.asarray(dataset.variables["y"][:], dtype=np.float64) * perspective
        col = np.rint((geo_x - scan_x[0]) / (scan_x[1] - scan_x[0])).astype(np.int64)
        row = np.rint((geo_y - scan_y[0]) / (scan_y[1] - scan_y[0])).astype(np.int64)
        valid = np.isfinite(geo_x) & np.isfinite(geo_y)
        valid &= (col >= 0) & (col < len(scan_x)) & (row >= 0) & (row < len(scan_y))
        temperature = np.full((height, width), np.nan, dtype=np.float32)
        if np.any(valid):
            r0, r1 = row[valid].min(), row[valid].max() + 1
            c0, c1 = col[valid].min(), col[valid].max() + 1
            cmi = np.asarray(dataset.variables["CMI"][r0:r1, c0:c1].filled(np.nan))
            dqf = np.asarray(dataset.variables["DQF"][r0:r1, c0:c1])
            sampled = cmi[row[valid] - r0, col[valid] - c0]
            quality = dqf[row[valid] - r0, col[valid] - c0] == 0
            temperature[valid] = np.where(quality, sampled - 273.15, np.nan)
    processed.parent.mkdir(parents=True, exist_ok=True)
    frame.parent.mkdir(parents=True, exist_ok=True)
    temporary_data = processed.with_suffix(".npz.part")
    with temporary_data.open("wb") as stream:
        np.savez_compressed(stream, temperature=temperature)
    temporary_data.replace(processed)
    slot = datetime.strptime(source.stem, "%Y%m%d%H%M").replace(tzinfo=UTC)
    _render_frame(temperature, slot, frame)


def _render_processed(processed: Path, frame: Path) -> None:
    import numpy as np

    with np.load(processed) as values:
        temperature = values["temperature"]
    slot = datetime.strptime(processed.stem, "%Y%m%d%H%M").replace(tzinfo=UTC)
    _render_frame(temperature, slot, frame)


def _cleanup(valid_ids: set[str]) -> None:
    for root, suffixes in (
        (RAW_ROOT, (".nc", ".part")),
        (PROCESSED_ROOT, (".npz", ".part")),
        (FRAME_ROOT, (".png", ".part")),
    ):
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if not path.is_file():
                continue
            is_cache_file = path.suffix in suffixes and FRAME_ID.fullmatch(path.name[:12])
            if not is_cache_file or path.name[:12] not in valid_ids:
                path.unlink(missing_ok=True)


def _render_version_is_current() -> bool:
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip() == str(RENDER_VERSION)
    except OSError:
        return False


def _ensure_render_version() -> bool:
    if _render_version_is_current():
        return False
    # Keep the last valid frames visible. They are replaced atomically from
    # newest to oldest instead of leaving the UI empty during a migration.
    VERSION_PATH.write_text(str(RENDER_VERSION), encoding="utf-8")
    return True


def refresh_cache(now: datetime | None = None) -> list[dict[str, str]]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if not owns_cache():
        return frame_catalog(current)
    slots = window_slots(current)
    valid_ids = {slot_id(slot) for slot in slots}
    if not _lock.acquire(blocking=False):
        return frame_catalog(current)
    try:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        migrating = _ensure_render_version()
        _cleanup(valid_ids)
        active_prefixes = {
            f"{PRODUCT}/{slot:%Y}/{slot:%j}/{slot:%H}/" for slot in slots
        }
        for prefix in list(_hour_listing):
            if prefix not in active_prefixes:
                del _hour_listing[prefix]
        hour_keys: dict[datetime, list[str]] = {}
        pending: list[tuple[str, Path, Path, Path]] = []
        for slot in slots:
            frame = FRAME_ROOT / f"{slot_id(slot)}.png"
            if not migrating and frame.is_file() and frame.stat().st_size > 0:
                continue
            hour = slot.replace(minute=0)
            if hour not in hour_keys:
                try:
                    hour_keys[hour] = _list_hour(hour, current)
                except (requests.RequestException, ET.ParseError) as error:
                    _logger.warning("GOES 19: no se pudo listar %s: %s", hour, error)
                    hour_keys[hour] = []
            matches = [key for key in hour_keys[hour] if key_slot(key) == slot]
            if not matches:
                continue
            key = max(matches)
            identifier = slot_id(slot)
            raw = RAW_ROOT / f"{identifier}.nc"
            processed = PROCESSED_ROOT / f"{identifier}.npz"
            pending.append((key, raw, processed, frame))

        # On a cold start the full three-hour window can exceed 400 MB. Make
        # the newest available scan usable first, then backfill older scans in
        # parallel. The completed PNG is immediately visible to the catalog.
        pending.sort(key=lambda item: item[1].stem, reverse=True)
        if pending:
            key, raw, processed, frame = pending.pop(0)
            try:
                if processed.is_file():
                    _render_processed(processed, frame)
                elif _download(key, raw):
                    _process(raw, processed, frame)
            except Exception as error:
                _logger.warning("GOES 19: falló la toma prioritaria %s: %s", raw.stem, error)
        uncached = []
        for key, raw, processed, frame in pending:
            if processed.is_file():
                try:
                    _render_processed(processed, frame)
                except Exception as error:
                    _logger.warning("GOES 19: no pudo regenerar %s: %s", processed.stem, error)
            else:
                uncached.append((key, raw, processed, frame))
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_download, key, raw): (raw, processed, frame)
                       for key, raw, processed, frame in uncached}
            for future in as_completed(futures):
                raw, processed, frame = futures[future]
                try:
                    if future.result():
                        _process(raw, processed, frame)
                except Exception as error:
                    _logger.warning("GOES 19: falló la toma %s: %s", raw.stem, error)
        current = datetime.now(UTC) if now is None else current
        slots = window_slots(current)
        valid_ids = {slot_id(slot) for slot in slots}
        _cleanup(valid_ids)
        state = {
            "updatedAt": current.isoformat(),
            "windowStart": slots[0].isoformat(),
            "windowEnd": slots[-1].isoformat(),
            "frames": [path.stem for path in sorted(FRAME_ROOT.glob("????????????.png"))],
            "rendererVersion": RENDER_VERSION,
        }
        temporary_state = STATE_PATH.with_suffix(".json.part")
        temporary_state.write_text(json.dumps(state), encoding="utf-8")
        temporary_state.replace(STATE_PATH)
        return frame_catalog(current)
    finally:
        _lock.release()


def frame_catalog(now: datetime | None = None) -> list[dict[str, str]]:
    valid_ids = {slot_id(slot) for slot in window_slots(now)}
    frames = []
    if not FRAME_ROOT.is_dir():
        return frames
    for path in sorted(FRAME_ROOT.glob("????????????.png")):
        if path.stem not in valid_ids or not path.is_file():
            continue
        stamp = datetime.strptime(path.stem, "%Y%m%d%H%M").replace(tzinfo=UTC)
        local = stamp.astimezone(LOCAL_TZ)
        frames.append({
            "id": path.stem,
            "localTime": local.isoformat(),
            "label": local.strftime("%H:%M"),
            "imageUrl": f"/api/goes19/frames/{path.stem}.png?v={RENDER_VERSION}",
        })
    return frames


def resolve_frame(frame_id: str) -> Path:
    if not FRAME_ID.fullmatch(frame_id):
        raise ValueError("Fotograma no válido")
    if frame_id not in {slot_id(slot) for slot in window_slots()}:
        raise FileNotFoundError(frame_id)
    path = FRAME_ROOT / f"{frame_id}.png"
    if not path.is_file():
        raise FileNotFoundError(frame_id)
    return path

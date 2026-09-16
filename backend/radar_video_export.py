from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .desktop_dialogs import choose_save_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAP_WIDTH, MAP_HEIGHT, HEADER_HEIGHT = 1600, 668, 90
RADAR_X, RADAR_Y = 694_951.002, 9_694_792.553
RADAR_EXTENT = (RADAR_X - 100_000, RADAR_Y - 100_000, RADAR_X + 100_000, RADAR_Y + 100_000)
AREA_BOUNDS = {
    "cuenca": (406_951, 9_559_793, 982_951, 9_799_793),
    "subcuencas": (605_974, 9_639_119, 804_528, 9_721_850),
    "urbana": (698_424, 9_671_257, 750_169, 9_692_836),
}
AREA_LABELS = {"cuenca": "Cantón Cuenca", "subcuencas": "Subcuencas", "urbana": "Zona urbana"}
BOUNDARY_SOURCES = {
    "cuenca": ("Cantones_Ecuador.gpkg", "cantones_Ecuador", 'WHERE CANTON = "CUENCA"'),
    "subcuencas": ("Subcuencas.gpkg", "sub_paute", ""),
    "urbana": ("ZonaUrbana.gpkg", "cuenca", ""),
}


def _ffmpeg_path() -> Path:
    candidates = [
        PROJECT_ROOT / "dependencies" / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path(sys.executable).resolve().parent.parent / "dependencies" / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return Path(system_ffmpeg)
    raise ValueError("No se encontró FFmpeg en las dependencias de Agender.")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arialbd.ttf" if bold else "arial.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _map_point(point: tuple[float, float], bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    west, south, east, north = bounds
    x, y = point
    return round((x - west) / (east - west) * MAP_WIDTH), round((north - y) / (north - south) * MAP_HEIGHT)


def _draw_boundaries(image: Image.Image, area: str) -> None:
    from .radar_caxx import AREA_SOURCE_ROOT, _gpkg_geometry

    filename, table, clause = BOUNDARY_SOURCES[area]
    with sqlite3.connect(AREA_SOURCE_ROOT / filename) as connection:
        rows = connection.execute(f'SELECT geom FROM "{table}" {clause}').fetchall()
    drawing = ImageDraw.Draw(image)
    for (blob,) in rows:
        for polygon in _gpkg_geometry(blob):
            for ring in polygon:
                points = [_map_point(point, AREA_BOUNDS[area]) for point in ring]
                if len(points) > 1:
                    drawing.line(points, fill=(255, 255, 255, 235), width=3, joint="curve")


def _draw_radar(image: Image.Image, frame_id: str, area: str) -> None:
    from .radar_caxx import resolve_area_frame

    with Image.open(resolve_area_frame(frame_id, area)) as source:
        radar = source.convert("RGBA")
    left, bottom = _map_point((RADAR_EXTENT[0], RADAR_EXTENT[1]), AREA_BOUNDS[area])
    right, top = _map_point((RADAR_EXTENT[2], RADAR_EXTENT[3]), AREA_BOUNDS[area])
    radar = radar.resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    image.alpha_composite(radar, (left, top))


def _draw_rings(image: Image.Image, area: str) -> None:
    drawing = ImageDraw.Draw(image)
    bounds = AREA_BOUNDS[area]
    center = _map_point((RADAR_X, RADAR_Y), bounds)
    west, south, east, north = bounds
    for radius, color in ((20_000, "#ffe600"), (60_000, "#00eaff"), (100_000, "#ff3f7f")):
        rx, ry = radius / (east - west) * MAP_WIDTH, radius / (north - south) * MAP_HEIGHT
        drawing.ellipse((center[0] - rx, center[1] - ry, center[0] + rx, center[1] + ry), outline=color, width=3)
    drawing.ellipse(
        (center[0] - 7, center[1] - 7, center[0] + 7, center[1] + 7),
        fill="#ffffff",
        outline="#073344",
        width=3,
    )


def _frame_time(frame_id: str) -> str:
    local = datetime.strptime(frame_id, "%Y%m%d%H%M").replace(tzinfo=UTC).astimezone(timezone(timedelta(hours=-5)))
    months = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    return f"{local.day:02d} {months[local.month - 1]} · {local:%H:%M}"


def _render_frame(frame_id: str, area: str, destination: Path) -> None:
    # The video uses real PNG files, as GOESHub does; no canvas/Base64 round trip.
    from .main import _radar_caxx_cached_basemap

    basemap = Image.open(BytesIO(_radar_caxx_cached_basemap(area))).convert("RGBA")
    basemap = basemap.resize((MAP_WIDTH, MAP_HEIGHT), Image.Resampling.LANCZOS)
    _draw_radar(basemap, frame_id, area)
    _draw_boundaries(basemap, area)
    _draw_rings(basemap, area)

    frame = Image.new("RGB", (MAP_WIDTH, HEADER_HEIGHT + MAP_HEIGHT), "#292929")
    frame.paste(basemap.convert("RGB"), (0, HEADER_HEIGHT))
    drawing = ImageDraw.Draw(frame)
    drawing.text((28, 17), "ÁREA DE VIGILANCIA", fill="#27c7dc", font=_font(15, True))
    drawing.text((28, 42), AREA_LABELS[area], fill="#f4f5f6", font=_font(26, True))
    drawing.text((MAP_WIDTH - 28, 18), _frame_time(frame_id), fill="#f4f5f6", font=_font(19, True), anchor="ra")
    drawing.text((MAP_WIDTH - 28, 52), "●  Radar Cuenca", fill="#c5cbcf", font=_font(14), anchor="ra")
    frame.save(destination, format="PNG", compress_level=4)


def _validate_frame_ids(frame_ids: list[str]) -> None:
    if not 2 <= len(frame_ids) <= 49:
        raise ValueError("El video debe contener entre 2 y 49 frames.")
    if any(len(value) != 12 or not value.isdigit() for value in frame_ids):
        raise ValueError("La secuencia contiene un fotograma no válido.")
    if frame_ids != sorted(frame_ids) or len(frame_ids) != len(set(frame_ids)):
        raise ValueError("Los fotogramas deben ser únicos y estar ordenados cronológicamente.")


def export_radar_mp4(frame_ids: list[str], area: str) -> dict[str, object]:
    if area not in AREA_BOUNDS:
        raise ValueError("Área de vigilancia no válida.")
    _validate_frame_ids(frame_ids)
    area_name = {"cuenca": "canton-cuenca", "subcuencas": "subcuencas", "urbana": "zona-urbana"}[area]
    output = choose_save_file(
        "Guardar animación del Radar Caxx", f"radar-caxx-{area_name}.mp4", ".mp4", [("Video MP4", "*.mp4")]
    )
    if output is None:
        return {"ok": False, "canceled": True, "message": "Exportación cancelada."}

    with tempfile.TemporaryDirectory(prefix="agender-radar-video-") as directory:
        temporary = Path(directory)
        for index, frame_id in enumerate(frame_ids, start=1):
            _render_frame(frame_id, area, temporary / f"frame_{index:04d}.png")
        encoded = temporary / "radar-caxx.mp4"
        command = [
            str(_ffmpeg_path()), "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", "2", "-i", str(temporary / "frame_%04d.png"),
            "-vf", "scale=1600:-2:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-profile:v", "high", "-level", "4.1",
            "-preset", "slow", "-crf", "18", "-movflags", "+faststart", str(encoded),
        ]
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(command, capture_output=True, check=False, creationflags=creation_flags)
        if result.returncode or not encoded.is_file() or not encoded.stat().st_size:
            message = result.stderr.decode(errors="replace").strip()
            raise ValueError(f"FFmpeg no pudo crear el MP4. {message}".strip())
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(encoded, output)
    return {"ok": True, "canceled": False, "path": str(output), "frames": len(frame_ids)}

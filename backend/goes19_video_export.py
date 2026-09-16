from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .desktop_dialogs import choose_save_file
from .goes19 import frame_catalog, resolve_frame


def _ffmpeg_path() -> Path:
    project_root = Path(__file__).resolve().parent.parent
    executable = Path(sys.executable).resolve()
    candidates = (
        project_root / "dependencies/ffmpeg/bin/ffmpeg.exe",
        executable.parent.parent / "dependencies/ffmpeg/bin/ffmpeg.exe",
        executable.parent / "dependencies/ffmpeg/bin/ffmpeg.exe",
        Path(getattr(sys, "_MEIPASS", executable.parent)) / "dependencies/ffmpeg/bin/ffmpeg.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return Path(system_ffmpeg)
    raise ValueError("No se encontró FFmpeg en las dependencias de Agender.")


def export_goes19_mp4(frame_ids: list[str]) -> dict[str, object]:
    if not 2 <= len(frame_ids) <= 19:
        raise ValueError("Se necesitan entre 2 y 19 imágenes GOES 19 para exportar.")
    if frame_ids != sorted(set(frame_ids)):
        raise ValueError("Las imágenes deben ser únicas y estar en orden cronológico.")
    available = {frame["id"] for frame in frame_catalog()}
    if any(frame_id not in available for frame_id in frame_ids):
        raise ValueError("Una imagen salió de la ventana de tres horas. Actualiza la secuencia.")

    output = choose_save_file(
        "Guardar animación GOES 19",
        f"goes19-c13-{frame_ids[-1]}.mp4",
        ".mp4",
        [("Video MP4", "*.mp4")],
    )
    if output is None:
        return {"ok": False, "canceled": True, "message": "Exportación cancelada."}

    with tempfile.TemporaryDirectory(prefix="agender-goes19-video-") as directory:
        temporary = Path(directory)
        for index, frame_id in enumerate(frame_ids, start=1):
            try:
                shutil.copy2(resolve_frame(frame_id), temporary / f"frame_{index:04d}.png")
            except FileNotFoundError as error:
                raise ValueError("Una imagen salió de la ventana de tres horas. Actualiza la secuencia.") from error
        encoded = temporary / "goes19-c13.mp4"
        command = [
            str(_ffmpeg_path()), "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", "2", "-i", str(temporary / "frame_%04d.png"),
            "-vf", "scale=960:-2:flags=lanczos,format=yuv420p",
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

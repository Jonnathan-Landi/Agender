from pathlib import Path

import pytest
from PIL import Image

from backend import goes19_video_export


def test_export_copies_cached_pngs_and_uses_goeshub_ffmpeg_settings(tmp_path, monkeypatch):
    ids = ["202608080800", "202608080810"]
    originals = []
    for index, frame_id in enumerate(ids):
        source = tmp_path / f"{frame_id}.png"
        source.write_bytes(f"png-{index}".encode())
        originals.append(source)
    output = tmp_path / "chosen" / "goes19.mp4"
    observed = {}

    monkeypatch.setattr(goes19_video_export, "frame_catalog", lambda: [{"id": value} for value in ids])
    monkeypatch.setattr(goes19_video_export, "resolve_frame", lambda value: originals[ids.index(value)])
    monkeypatch.setattr(goes19_video_export, "choose_save_file", lambda *_args: output)
    monkeypatch.setattr(goes19_video_export, "_ffmpeg_path", lambda: tmp_path / "ffmpeg.exe")

    def run(command, **_kwargs):
        observed["frames"] = [
            (Path(command[command.index("-i") + 1]).parent / f"frame_{index:04d}.png").read_bytes()
            for index in (1, 2)
        ]
        observed["command"] = command
        Path(command[-1]).write_bytes(b"mp4")
        return type("Result", (), {"returncode": 0, "stderr": b""})()

    monkeypatch.setattr(goes19_video_export.subprocess, "run", run)
    result = goes19_video_export.export_goes19_mp4(ids)

    assert result == {"ok": True, "canceled": False, "path": str(output), "frames": 2}
    assert output.read_bytes() == b"mp4"
    assert observed["frames"] == [b"png-0", b"png-1"]
    command = observed["command"]
    assert command[command.index("-framerate") + 1] == "2"
    assert command[command.index("-vf") + 1] == "scale=960:-2:flags=lanczos,format=yuv420p"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-preset") + 1] == "slow"
    assert command[command.index("-crf") + 1] == "18"
    assert "+faststart" in command


def test_export_rejects_stale_or_unordered_frames_and_honors_cancel(monkeypatch):
    ids = ["202608080800", "202608080810"]
    monkeypatch.setattr(goes19_video_export, "frame_catalog", lambda: [{"id": value} for value in ids])
    monkeypatch.setattr(goes19_video_export, "choose_save_file", lambda *_args: None)
    assert goes19_video_export.export_goes19_mp4(ids)["canceled"] is True
    with pytest.raises(ValueError, match="cronológico"):
        goes19_video_export.export_goes19_mp4(ids[::-1])
    with pytest.raises(ValueError, match="ventana"):
        goes19_video_export.export_goes19_mp4([ids[0], "202608080820"])


def test_bundled_ffmpeg_produces_playable_mp4(tmp_path, monkeypatch):
    ffmpeg = goes19_video_export._ffmpeg_path()
    if not ffmpeg.is_file():
        pytest.skip("FFmpeg empaquetado no disponible")
    ids = ["202608080800", "202608080810"]
    sources = {}
    for index, frame_id in enumerate(ids):
        path = tmp_path / f"{frame_id}.png"
        Image.new("RGB", (64, 64), (index * 120, 40, 80)).save(path)
        sources[frame_id] = path
    output = tmp_path / "goes19.mp4"
    monkeypatch.setattr(goes19_video_export, "frame_catalog", lambda: [{"id": value} for value in ids])
    monkeypatch.setattr(goes19_video_export, "resolve_frame", lambda value: sources[value])
    monkeypatch.setattr(goes19_video_export, "choose_save_file", lambda *_args: output)

    result = goes19_video_export.export_goes19_mp4(ids)

    assert result["ok"] is True
    assert output.stat().st_size > 1000
    assert b"ftyp" in output.read_bytes()[:64]

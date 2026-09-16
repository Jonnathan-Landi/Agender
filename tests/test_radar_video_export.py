from pathlib import Path

import pytest

from backend import radar_video_export


def test_validate_frame_ids_rejects_invalid_or_unordered_sequences():
    with pytest.raises(ValueError):
        radar_video_export._validate_frame_ids(["not-a-frame", "202608010005"])
    with pytest.raises(ValueError):
        radar_video_export._validate_frame_ids(["202608010005", "202608010000"])
    with pytest.raises(ValueError):
        radar_video_export._validate_frame_ids(["202608010000", "202608010000"])


def test_export_renders_disk_sequence_and_uses_goeshub_parameters(tmp_path, monkeypatch):
    output = tmp_path / "radar.mp4"
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"exe")
    observed = {"rendered": []}

    def render(frame_id, area, destination):
        observed["rendered"].append((frame_id, area, destination.name))
        destination.write_bytes(b"png")

    def run(command, **kwargs):
        observed["command"] = command
        Path(command[-1]).write_bytes(b"mp4")
        return type("Result", (), {"returncode": 0, "stderr": b""})()

    monkeypatch.setattr(radar_video_export, "choose_save_file", lambda *_args: output)
    monkeypatch.setattr(radar_video_export, "_ffmpeg_path", lambda: ffmpeg)
    monkeypatch.setattr(radar_video_export, "_render_frame", render)
    monkeypatch.setattr(radar_video_export.subprocess, "run", run)

    ids = ["202608010000", "202608010005"]
    result = radar_video_export.export_radar_mp4(ids, "urbana")

    assert result == {"ok": True, "canceled": False, "path": str(output), "frames": 2}
    assert output.read_bytes() == b"mp4"
    assert observed["rendered"] == [
        (ids[0], "urbana", "frame_0001.png"),
        (ids[1], "urbana", "frame_0002.png"),
    ]
    command = observed["command"]
    assert "libx264" in command
    assert "scale=1600:-2:flags=lanczos,format=yuv420p" in command
    assert command[command.index("-preset") + 1] == "slow"
    assert command[command.index("-crf") + 1] == "18"
    assert "+faststart" in command

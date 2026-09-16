from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from PIL import Image

from backend import radar_caxx


def test_window_contains_exactly_four_hours_in_five_minute_steps():
    now = datetime(2026, 8, 31, 2, 7, tzinfo=UTC)
    slots = radar_caxx.window_times(now)

    assert len(slots) == 49
    assert slots[0][0].strftime("%H:%M") == "17:05"
    assert slots[-1][0].strftime("%H:%M") == "21:05"
    assert all((right[0] - left[0]).total_seconds() == 300 for left, right in pairwise(slots))


def test_source_url_uses_utc_date_and_expected_filename():
    instant = datetime(2026, 8, 31, 2, 5, tzinfo=UTC)
    url, filename = radar_caxx.source_url(100, instant)

    assert filename == "2026083102050000dBuZ.ppi_top.gif"
    assert url.endswith(f"/100km/2026-08-31/{filename}")


def test_composite_places_scopes_on_transparent_utm_canvas(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    frame_root = tmp_path / "frames"
    monkeypatch.setattr(radar_caxx, "SOURCE_ROOT", source_root)
    monkeypatch.setattr(radar_caxx, "FRAME_ROOT", frame_root)
    instant = datetime(2026, 8, 31, 2, 5, tzinfo=UTC)

    for scope, color in ((100, (255, 0, 0, 180)), (60, (0, 255, 0, 180)), (20, (0, 0, 255, 255))):
        _, filename = radar_caxx.source_url(scope, instant)
        path = source_root / f"{scope}km" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", (20, 20), color)
        image.convert("P", palette=Image.Palette.ADAPTIVE).save(path)

    output = radar_caxx.compose_frame(instant)

    assert output == frame_root / "202608310205.png"
    assert output.is_file()
    with Image.open(output) as composite:
        assert composite.size == (2000, 2000)
        assert composite.mode == "RGBA"
        assert composite.getbbox() is not None
        assert composite.getpixel((1000, 1000))[:3] == (0, 0, 255)
        assert composite.getpixel((1400, 1000))[:3] == (0, 255, 0)
        assert composite.getpixel((1800, 1000))[:3] == (255, 0, 0)
        assert composite.getpixel((0, 0))[3] == 0


def test_resolve_frame_rejects_paths_and_unknown_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(radar_caxx, "FRAME_ROOT", Path(tmp_path))

    for invalid in ("../../secret", "20260831020x", "2026083102050"):
        try:
            radar_caxx.resolve_frame(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted invalid frame id: {invalid}")


def test_area_product_preserves_canvas_and_masks_outside_geometry(tmp_path, monkeypatch):
    frame_root = tmp_path / "frames"
    monkeypatch.setattr(radar_caxx, "FRAME_ROOT", frame_root)
    source = frame_root / "202608310205.png"
    source.parent.mkdir(parents=True)
    Image.new("RGBA", (2000, 2000), (255, 0, 0, 255)).save(source)

    output = radar_caxx.resolve_area_frame("202608310205", "urbana")

    with Image.open(output) as product:
        assert product.size == (2000, 2000)
        assert product.getpixel((0, 0))[3] == 0
        assert product.getbbox() is not None

from contextlib import ExitStack
from datetime import UTC, datetime
from unittest.mock import patch

import numpy as np
import pytest
import requests

from backend import goes19


@pytest.fixture
def cache(tmp_path):
    with ExitStack() as stack:
        for name, suffix in {
            "CACHE_ROOT": "", "RAW_ROOT": "raw", "PROCESSED_ROOT": "processed",
            "FRAME_ROOT": "frames", "STATE_PATH": "state.json", "VERSION_PATH": ".render-version",
        }.items():
            stack.enter_context(patch.object(goes19, name, tmp_path / suffix))
        stack.enter_context(patch.object(goes19, "owns_cache", return_value=True))
        stack.enter_context(patch.object(goes19, "_hour_listing", {}))
        stack.enter_context(patch.object(goes19, "_status", {}))
        stack.enter_context(patch.object(goes19, "_no_data_until", {}))
        yield tmp_path


def key(slot):
    return f"ABI-L2-CMIPF/{slot:%Y/%j/%H}/OR_ABI-L2-CMIPF-M6C13_G19_s{slot:%Y%j%H%M}000_e.nc"


def test_newest_published_before_older_hour_listing_and_backfill_is_bounded(cache):
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    slots = goes19.window_slots(now)
    events = []

    def listing(hour, current):
        events.append(("list", hour))
        return [key(slot) for slot in slots if slot.replace(minute=0) == hour]

    def download(remote, raw):
        raw.parent.mkdir(exist_ok=True)
        raw.write_bytes(b"download")
        return True

    def process(raw, processed, frame):
        events.append(("process", raw.stem))
        frame.parent.mkdir(exist_ok=True)
        frame.write_bytes(b"image")

    with (patch.object(goes19, "_list_hour", side_effect=listing),
          patch.object(goes19, "_download", side_effect=download),
          patch.object(goes19, "_process", side_effect=process)):
        first = goes19.refresh_cache(now)
        assert len(first) == goes19.MAX_BATCH
        assert events[0] == ("list", now)
        assert events[1] == ("process", goes19.slot_id(now))
        assert goes19.cache_status()["phase"] == "backfill"
        for _ in range(4):
            goes19.refresh_cache(now)
    assert len(goes19.frame_catalog(now)) == 19
    assert len([event for event in events if event[0] == "process"]) == 19
    assert goes19.cache_status()["phase"] == "ready"


def test_noaa_unpublished_current_scan_does_not_leave_busy_status(cache):
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    with patch.object(goes19, "_list_hour", return_value=[]):
        assert goes19.refresh_cache(now) == []
    assert goes19.cache_status()["phase"] == "ready"
    assert goes19.cache_status()["pending"] == 0


def test_network_failure_is_reported_to_ui(cache):
    with patch.object(goes19, "_list_hour", side_effect=requests.ConnectionError("Sin conexión")):
        goes19.refresh_cache(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
    assert goes19.cache_status()["phase"] == "error"
    assert "Sin conexión" in goes19.cache_status()["message"]
    assert goes19.cache_status()["unpublishedFrames"] == []


def test_ssl_failure_is_identified_without_disabling_verification(cache):
    error = requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED")
    with patch.object(goes19, "_list_hour", side_effect=error):
        goes19.refresh_cache(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
    status = goes19.cache_status()
    assert status["phase"] == "error"
    assert "HTTPS" in status["message"]
    assert "SSL" in status["message"]
    assert status["error"] == "CERTIFICATE_VERIFY_FAILED"
    assert status["unpublishedFrames"] == []


def test_cached_raster_can_render_even_when_noaa_is_offline(cache):
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    goes19.PROCESSED_ROOT.mkdir()
    np.savez(goes19.PROCESSED_ROOT / f"{goes19.slot_id(now)}.npz", temperature=np.ones((2, 2)))

    def render(processed, frame):
        frame.parent.mkdir(exist_ok=True)
        frame.write_bytes(b"image")

    with (patch.object(goes19, "_list_hour", side_effect=requests.ConnectionError("Offline")),
          patch.object(goes19, "_render_processed", side_effect=render)):
        frames = goes19.refresh_cache(now)
    assert [item["id"] for item in frames] == [goes19.slot_id(now)]


def test_corrupt_processed_cache_is_rebuilt_from_raw(tmp_path):
    raw, processed, frame = [tmp_path / name for name in ("a.nc", "a.npz", "a.png")]
    raw.write_bytes(b"valid raw")
    processed.write_bytes(b"broken cache")
    with (patch.object(goes19, "_render_processed", side_effect=ValueError("Invalid NPZ")),
          patch.object(goes19, "_process") as process):
        goes19._prepare_frame(None, raw, processed, frame)
    process.assert_called_once_with(raw, processed, frame)
    assert not processed.exists()


def test_download_has_total_deadline_and_cleans_partial_file(tmp_path):
    from unittest.mock import MagicMock
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.iter_content.return_value = iter([b"data"])
    with (patch.object(goes19.requests, "get", return_value=response),
          patch.object(goes19.time, "monotonic", side_effect=[0, 121])):
        with pytest.raises(requests.Timeout):
            goes19._download("test.nc", tmp_path / "a.nc")
    assert not list(tmp_path.iterdir())


def test_late_publication_is_added_without_downloading_ready_frames_again(cache):
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    previous = now - goes19.INTERVAL
    published = [key(previous)]
    downloaded = []

    def download(remote, raw):
        downloaded.append(raw.stem)
        raw.parent.mkdir(exist_ok=True)
        raw.write_bytes(b"data")
        return True

    def process(raw, processed, frame):
        frame.parent.mkdir(exist_ok=True)
        frame.write_bytes(b"image")

    with (patch.object(goes19, "window_slots", return_value=[previous, now]),
          patch.object(goes19, "_list_hour", side_effect=lambda *_: list(published)),
          patch.object(goes19, "_download", side_effect=download),
          patch.object(goes19, "_process", side_effect=process)):
        assert len(goes19.refresh_cache(now)) == 1
        assert goes19.cache_status()["unpublishedFrames"] == [goes19.slot_id(now)]
        assert "NOAA aún no ha publicado" in goes19.cache_status()["message"]
        assert "07:00" in goes19.cache_status()["message"]
        published.append(key(now))
        assert len(goes19.refresh_cache(now)) == 2
        assert goes19.cache_status()["unpublishedFrames"] == []
    assert downloaded == [goes19.slot_id(previous), goes19.slot_id(now)]


def test_empty_temperature_is_not_rendered_or_published(cache):
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    frame = cache / "empty.png"
    with pytest.raises(goes19.NoSatelliteData):
        goes19._render_frame(np.full((10, 10), np.nan), now, frame)
    assert not frame.exists()
    goes19.PROCESSED_ROOT.mkdir()
    goes19.FRAME_ROOT.mkdir()
    for index, slot in enumerate(goes19.window_slots(now)[-2:]):
        name = goes19.slot_id(slot)
        np.savez(goes19.PROCESSED_ROOT / f"{name}.npz",
                 temperature=np.full((2, 2), np.nan if index else 10.0))
        (goes19.FRAME_ROOT / f"{name}.png").write_bytes(b"cached image")
    assert len(goes19.frame_catalog(now)) == 1
    with patch.object(goes19, "window_slots", return_value=[now]):
        with pytest.raises(FileNotFoundError):
            goes19.resolve_frame(goes19.slot_id(now))


def test_no_data_scan_is_omitted_and_retried_after_cooldown(cache):
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    name = goes19.slot_id(now)

    def download(remote, raw):
        raw.parent.mkdir(exist_ok=True)
        raw.write_bytes(b"raw")
        return True

    with (patch.object(goes19, "window_slots", return_value=[now]),
          patch.object(goes19, "_list_hour", return_value=[key(now)]),
          patch.object(goes19, "_download", side_effect=download) as downloaded,
          patch.object(goes19, "_process", side_effect=goes19.NoSatelliteData("Sin datos"))):
        assert goes19.refresh_cache(now) == []
        assert goes19.cache_status()["unavailableFrames"] == [name]
        assert "sin datos válidos" in goes19.cache_status()["message"]
        goes19.refresh_cache(now + goes19.INTERVAL / 2)
        assert downloaded.call_count == 1
        goes19.refresh_cache(now + goes19.INTERVAL)
        assert downloaded.call_count == 2
    assert not (goes19.RAW_ROOT / f"{name}.nc").exists()

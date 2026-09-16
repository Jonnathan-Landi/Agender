from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from backend import goes19


class Goes19Tests(unittest.TestCase):
    def test_ten_minute_slots_and_one_minute_retries(self) -> None:
        at_slot = datetime(2026, 9, 15, 18, 0, tzinfo=UTC)
        self.assertEqual(at_slot, goes19.floor_slot(at_slot))
        self.assertEqual(
            datetime(2026, 9, 15, 18, 1, tzinfo=UTC),
            goes19.next_refresh_time(at_slot, False),
        )
        fourth_attempt = at_slot + timedelta(minutes=3, seconds=4)
        self.assertEqual(
            at_slot + timedelta(minutes=4),
            goes19.next_refresh_time(fourth_attempt, False),
        )
        self.assertEqual(
            at_slot + timedelta(minutes=10),
            goes19.next_refresh_time(fourth_attempt, True),
        )

    def test_three_hour_window_advances_and_expires_old_slot(self) -> None:
        at_six = datetime(2026, 9, 15, 23, 0, tzinfo=UTC)
        initial = goes19.window_slots(at_six)
        shifted = goes19.window_slots(at_six + timedelta(minutes=10))
        self.assertEqual(19, len(initial))
        self.assertEqual(at_six - timedelta(hours=3), initial[0])
        self.assertEqual(at_six - timedelta(hours=3, minutes=-10), shifted[0])
        self.assertNotIn(initial[0], shifted)

    def test_noaa_channel_13_filename_is_grouped_by_scan_start(self) -> None:
        key = (
            "ABI-L2-CMIPF/2026/259/18/"
            "OR_ABI-L2-CMIPF-M6C13_G19_"
            "s20262591800202_e20262591809521_c20262591809568.nc"
        )
        self.assertEqual(
            datetime(2026, 9, 16, 18, 0, tzinfo=UTC),
            goes19.key_slot(key),
        )

    def test_cleanup_removes_raw_processed_and_rendered_outside_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, processed, frames = (root / name for name in ("raw", "processed", "frames"))
            for folder, extension in ((raw, ".nc"), (processed, ".npz"), (frames, ".png")):
                folder.mkdir()
                (folder / f"202609151500{extension}").write_bytes(b"old")
                (folder / f"202609151810{extension}").write_bytes(b"current")
            with (
                patch.object(goes19, "RAW_ROOT", raw),
                patch.object(goes19, "PROCESSED_ROOT", processed),
                patch.object(goes19, "FRAME_ROOT", frames),
            ):
                goes19._cleanup({"202609151810"})
            for folder, extension in ((raw, ".nc"), (processed, ".npz"), (frames, ".png")):
                self.assertFalse((folder / f"202609151500{extension}").exists())
                self.assertTrue((folder / f"202609151810{extension}").exists())

    def test_renderer_migration_keeps_last_frame_visible_until_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processed, frames = root / "processed", root / "frames"
            processed.mkdir()
            frames.mkdir()
            old_frame = frames / "202609151810.png"
            old_frame.write_bytes(b"old-design")
            (frames / "ui-audit.html").write_text("old audit", encoding="utf-8")
            (processed / "legacy.bin").write_bytes(b"old")
            version = root / ".render-version"
            state = root / "state.json"
            version.write_text(str(goes19.RENDER_VERSION - 1), encoding="utf-8")
            state.write_text("{}", encoding="utf-8")
            with (
                patch.object(goes19, "PROCESSED_ROOT", processed),
                patch.object(goes19, "FRAME_ROOT", frames),
                patch.object(goes19, "VERSION_PATH", version),
                patch.object(goes19, "STATE_PATH", state),
            ):
                self.assertEqual(1, len(goes19.frame_catalog(datetime(2026, 9, 15, 18, 10, tzinfo=UTC))))
                goes19._ensure_render_version()
            self.assertTrue(old_frame.exists())
            self.assertTrue((frames / "ui-audit.html").exists())
            self.assertTrue((processed / "legacy.bin").exists())
            self.assertTrue(state.exists())
            self.assertEqual(str(goes19.RENDER_VERSION), version.read_text(encoding="utf-8"))

    def test_only_latest_backend_instance_owns_the_goes_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            owner = Path(directory) / ".worker-owner"
            with patch.object(goes19, "OWNER_PATH", owner):
                goes19.claim_cache_ownership()
                self.assertTrue(goes19.owns_cache())
                owner.write_text("another-backend", encoding="utf-8")
                self.assertFalse(goes19.owns_cache())
                goes19.release_cache_ownership()
                self.assertTrue(owner.exists())

    def test_frame_embeds_goeshub_composition_at_native_square_size(self) -> None:
        self.assertAlmostEqual((800_000 + 149_271.6) / 1.7, goes19.GOES_VIEW_SIDE)
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "reference.png"
            values = np.full((20, 20), 10.0, dtype=np.float32)
            goes19._render_frame(values, datetime(2026, 8, 8, 8, tzinfo=UTC), frame)
            with Image.open(frame) as image:
                self.assertEqual((2000, 2000), image.size)
                self.assertEqual((0, 0, 0), image.getpixel((1500, 10)))
                self.assertGreater(min(image.getpixel((30, 1750))), 180)
                self.assertNotEqual((0, 0, 0), image.getpixel((800, 800)))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend import browser_render


class BrowserRenderTests(unittest.TestCase):
    def test_wait_for_images_rejects_broken_image_resources(self) -> None:
        page = MagicMock()

        browser_render.wait_for_images(page)

        expression = page.wait_for_function.call_args.args[0]
        self.assertIn('!image.getAttribute("src")', expression)
        self.assertIn("image.complete", expression)
        self.assertIn("image.naturalWidth > 0", expression)
        self.assertIn("image.naturalHeight > 0", expression)

    def test_bundled_browser_path_is_selected_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            browser_path = Path(directory)
            with (
                patch.object(browser_render, "BUNDLED_BROWSERS", browser_path),
                patch.dict(os.environ, {}, clear=False),
            ):
                os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
                browser_render._configure_bundled_browser()
                self.assertEqual(
                    str(browser_path),
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"],
                )

    def test_development_browser_path_is_selected_as_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_bundle = Path(directory) / "missing"
            development_path = Path(directory) / "build-browsers"
            development_path.mkdir()
            with (
                patch.object(browser_render, "BUNDLED_BROWSERS", missing_bundle),
                patch.object(browser_render, "DEVELOPMENT_BROWSERS", development_path),
                patch.dict(os.environ, {}, clear=False),
            ):
                os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
                browser_render._configure_bundled_browser()
                self.assertEqual(
                    str(development_path),
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"],
                )

    def test_packaging_installs_and_embeds_controlled_chromium(self) -> None:
        root = Path(__file__).resolve().parent.parent
        build_script = (root / "scripts" / "build-backend.ps1").read_text(encoding="utf-8")
        specification = (
            root / "packaging" / "agender-backend.spec"
        ).read_text(encoding="utf-8")
        entrypoint = (root / "packaging" / "backend_entry.py").read_text(encoding="utf-8")
        release_script = (root / "scripts" / "build-release.ps1").read_text(encoding="utf-8")

        self.assertIn("playwright install chromium --only-shell", build_script)
        self.assertIn('"playwright-browsers"', specification)
        self.assertIn("--render-smoke-test", entrypoint)
        self.assertIn("--climatology-smoke-test", entrypoint)
        self.assertIn("resolve-windows-sdk.ps1", release_script)

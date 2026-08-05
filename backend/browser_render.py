from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, Error as PlaywrightError, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_BROWSERS = PROJECT_ROOT / "playwright-browsers"
DEVELOPMENT_BROWSERS = PROJECT_ROOT / "build" / "playwright-browsers"


def _configure_bundled_browser() -> None:
    for browser_path in (BUNDLED_BROWSERS, DEVELOPMENT_BROWSERS):
        if browser_path.is_dir():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_path)
            return


@contextmanager
def chromium_browser() -> Iterator[Browser]:
    _configure_bundled_browser()
    playwright = None
    try:
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError:
            executable = _installed_browser()
            if executable is None:
                raise
            browser = playwright.chromium.launch(headless=True, executable_path=str(executable))
    except PlaywrightError as error:
        if playwright is not None:
            playwright.stop()
        raise ValueError("No se pudo iniciar el motor de exportación integrado.") from error
    try:
        yield browser
    finally:
        try:
            browser.close()
        finally:
            playwright.stop()


def _installed_browser() -> Path | None:
    candidates = (
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def wait_for_images(page, timeout: int = 20_000) -> None:
    page.wait_for_function(
        """() => Array.from(document.images).every(image =>
            !image.getAttribute("src") ||
            (image.complete && image.naturalWidth > 0 && image.naturalHeight > 0)
        )""",
        timeout=timeout,
    )


def render_smoke_test() -> dict[str, int | bool]:
    with tempfile.TemporaryDirectory(prefix="agender-render-smoke-") as temporary:
        root = Path(temporary)
        pdf_path = root / "smoke.pdf"
        image_path = root / "smoke.png"
        with chromium_browser() as browser:
            page = browser.new_page(viewport={"width": 320, "height": 180})
            page.set_content(
                "<!doctype html><html><body><h1>Agender</h1></body></html>",
                wait_until="load",
            )
            page.pdf(path=str(pdf_path), print_background=True)
            page.screenshot(path=str(image_path), type="png")
        pdf_size = pdf_path.stat().st_size if pdf_path.is_file() else 0
        image_size = image_path.stat().st_size if image_path.is_file() else 0
        return {
            "ok": pdf_size > 0 and image_size > 0,
            "pdfBytes": pdf_size,
            "imageBytes": image_size,
        }

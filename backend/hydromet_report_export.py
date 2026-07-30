from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .browser_render import chromium_browser, wait_for_images
from .desktop_dialogs import choose_directory

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_CSS = PROJECT_ROOT / "frontend" / "css" / "hydromet-report.css"
REPORT_ASSET_DIR = PROJECT_ROOT / "frontend" / "assets" / "hydromet-report"
EXPORT_SIZE = 4167
MAX_EXPORT_HTML_BYTES = 45 * 1024 * 1024
REPORT_LABELS = {
    "caudales": "Caudales",
    "lluvias": "Lluvias por estaciones",
    "temperaturas": "Temperaturas",
    "pronostico-diario": "Pronóstico diario",
    "pronostico-semanal": "Pronóstico semanal",
    "indice-ultravioleta": "Índice ultravioleta",
}
REPORT_TEMPLATES = {
    "caudales": "01-caudales.jpeg",
    "lluvias": "02-lluvias.jpeg",
    "temperaturas": "03-temperaturas.jpeg",
    "pronostico-diario": "04-pronostico-diario.jpeg",
    "pronostico-semanal": "05-pronostico-semanal.jpeg",
    "indice-ultravioleta": "06-indice-ultravioleta.jpeg",
}


def export_hydromet_designs(
    reports: list[dict[str, Any]],
    report_date: date,
    report_time: str,
) -> dict[str, object]:
    normalized = _validate_reports(reports)
    if not REPORT_CSS.is_file():
        raise ValueError("No se encontró la hoja de estilos del reporte hidrometeorológico.")
    try:
        selected_root = choose_directory("Selecciona la carpeta para guardar los diseños")
    except Exception as error:
        raise ValueError(
            "No se pudo abrir la ventana para seleccionar la carpeta. Reinicia Agender y vuelve a intentarlo."
        ) from error
    if selected_root is None:
        return {"ok": False, "canceled": True, "message": "Exportación cancelada."}

    folder_stem = f"{report_date.isoformat()}_{report_time.replace(':', '')}"
    output_folder = _available_folder(selected_root, folder_stem)
    staging_folder = selected_root / f".agender-export-{uuid.uuid4().hex}"
    staging_folder.mkdir(parents=False, exist_ok=False)
    exported_files: list[str] = []
    try:
        css = REPORT_CSS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="agender-hydromet-export-") as temporary:
            temporary_path = Path(temporary)
            with chromium_browser() as browser:
                page = browser.new_page(
                    viewport={"width": EXPORT_SIZE, "height": EXPORT_SIZE}
                )
                for index, report in enumerate(normalized):
                    report_key = report["format"]
                    document = _build_capture_document(
                        report["html"],
                        css,
                        report_key,
                    )
                    html_path = temporary_path / f"{index:02d}-{report_key}.html"
                    png_path = temporary_path / f"{index:02d}-{report_key}.png"
                    html_path.write_text(document, encoding="utf-8")
                    _capture_page(page, html_path, png_path)

                    filename = f"{report_key}_{report_date.isoformat()}.jpg"
                    _save_maximum_quality_jpeg(
                        png_path,
                        staging_folder / filename,
                        _report_template_path(report_key),
                    )
                    exported_files.append(filename)

        staging_folder.replace(output_folder)
    except Exception:
        shutil.rmtree(staging_folder, ignore_errors=True)
        raise

    return {
        "ok": True,
        "canceled": False,
        "folder": str(output_folder),
        "folderName": output_folder.name,
        "files": exported_files,
        "count": len(exported_files),
        "message": f"Se exportaron {len(exported_files)} diseños.",
    }


def _validate_reports(reports: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not 1 <= len(reports) <= len(REPORT_LABELS):
        raise ValueError("Selecciona entre uno y seis diseños para exportar.")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    total_bytes = 0
    for report in reports:
        report_key = str(report.get("format", "")).strip()
        report_html = str(report.get("html", "")).strip()
        if report_key not in REPORT_LABELS:
            raise ValueError("La selección contiene un diseño no reconocido.")
        if report_key in seen:
            raise ValueError("No se puede exportar el mismo diseño más de una vez.")
        if not report_html:
            raise ValueError(f"El diseño {REPORT_LABELS[report_key]} está vacío.")
        total_bytes += len(report_html.encode("utf-8"))
        if total_bytes > MAX_EXPORT_HTML_BYTES:
            raise ValueError("Los diseños seleccionados superan el tamaño permitido.")
        seen.add(report_key)
        normalized.append({"format": report_key, "html": report_html})
    return normalized


def _available_folder(root: Path, stem: str) -> Path:
    candidate = root / stem
    suffix = 2
    while candidate.exists():
        candidate = root / f"{stem}_{suffix:02d}"
        suffix += 1
    return candidate


def _sanitize_report_html(value: str) -> str:
    sanitized = re.sub(
        r"<\s*(script|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>",
        "",
        value,
        flags=re.I | re.S,
    )
    sanitized = re.sub(
        r"<\s*(script|iframe|object|embed)\b[^>]*/?\s*>",
        "",
        sanitized,
        flags=re.I | re.S,
    )
    return re.sub(
        r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "",
        sanitized,
        flags=re.I,
    )


def _build_capture_document(
    report_html: str,
    report_css: str,
    report_key: str | None = None,
) -> str:
    safe_report = _sanitize_report_html(report_html)
    if report_key is not None:
        safe_report = _remove_report_template(safe_report)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <style>{report_css}</style>
  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    html, body {{
      width: {EXPORT_SIZE}px !important;
      height: {EXPORT_SIZE}px !important;
      margin: 0 !important;
      padding: 0 !important;
      overflow: hidden !important;
      background: transparent !important;
    }}
    .hydromet-report-page {{
      display: block !important;
      width: {EXPORT_SIZE}px !important;
      height: {EXPORT_SIZE}px !important;
      margin: 0 !important;
      overflow: hidden !important;
      border: 0 !important;
      border-radius: 0 !important;
      box-shadow: none !important;
      background: transparent !important;
    }}
    .hydromet-upload-zone, .hydromet-crop-overlay,
    .hydromet-generated-map-status, input[type="file"] {{
      display: none !important;
    }}
    .hydromet-inserted-image, .hydromet-image-slot {{
      outline: 0 !important;
      box-shadow: none !important;
    }}
  </style>
</head>
<body>{safe_report}</body>
</html>"""


def _report_template_path(report_key: str) -> Path:
    filename = REPORT_TEMPLATES.get(report_key)
    if filename is None:
        raise ValueError("El diseño no tiene una plantilla base reconocida.")
    template_path = REPORT_ASSET_DIR / filename
    if not template_path.is_file():
        raise ValueError(f"No se encontró la plantilla base {filename}.")
    return template_path


def _remove_report_template(report_html: str) -> str:
    template_pattern = re.compile(
        r"""<img\b(?=[^>]*\bclass\s*=\s*(?:"[^"]*\bhydromet-report-template\b[^"]*"|'[^']*\bhydromet-report-template\b[^']*'))[^>]*>""",
        flags=re.I,
    )
    stripped, count = template_pattern.subn("", report_html, count=1)
    if count != 1:
        raise ValueError("El diseño no contiene su imagen de plantilla base.")
    return stripped


def _capture_page(
    page,
    html_path: Path,
    png_path: Path,
) -> None:
    try:
        page.goto(html_path.as_uri(), wait_until="load", timeout=30_000)
        wait_for_images(page)
        page.screenshot(
            path=str(png_path),
            type="png",
            full_page=False,
            animations="disabled",
            omit_background=True,
        )
    except PlaywrightTimeoutError as error:
        raise ValueError(
            "El motor de exportación tardó demasiado en preparar uno de los diseños."
        ) from error
    if not png_path.is_file() or png_path.stat().st_size == 0:
        raise ValueError("El motor de exportación no produjo una imagen válida.")


def _save_maximum_quality_jpeg(
    source: Path,
    destination: Path,
    template: Path,
) -> None:
    with Image.open(template) as template_image, Image.open(source) as overlay_image:
        base = template_image.convert("RGBA")
        if base.size != (EXPORT_SIZE, EXPORT_SIZE):
            base = base.resize((EXPORT_SIZE, EXPORT_SIZE), Image.Resampling.LANCZOS)
        overlay = overlay_image.convert("RGBA")
        if overlay.size != base.size:
            overlay = overlay.resize(base.size, Image.Resampling.LANCZOS)
        base.alpha_composite(overlay)
        base.convert("RGB").save(
            destination,
            format="JPEG",
            quality=100,
            subsampling=0,
            optimize=True,
            dpi=(300, 300),
        )

from __future__ import annotations

import html
import re
import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .browser_render import chromium_browser, wait_for_images
from .desktop_dialogs import choose_save_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_CSS = PROJECT_ROOT / "frontend" / "wqreport" / "css" / "style.css"
REPORT_WIDTH = 1850
REPORT_MIN_HEIGHT = 1260
CSS_PIXELS_PER_INCH = 96
MAX_REPORT_HTML_BYTES = 40 * 1024 * 1024


def export_report_pdf(
    reports_html: str,
    suggested_file_name: str,
    page_height: int,
    assets_base_url: str,
) -> dict[str, object]:
    if not reports_html.strip():
        raise ValueError("No se recibió contenido para exportar.")
    if len(reports_html.encode("utf-8")) > MAX_REPORT_HTML_BYTES:
        raise ValueError("El reporte supera el tamaño máximo permitido para exportar.")
    if not REPORT_CSS.is_file():
        raise ValueError("No se encontró la hoja de estilos de WQReport.")

    safe_name = _safe_file_name(suggested_file_name)
    try:
        output = choose_save_file(
            "Guardar reporte en PDF",
            f"{safe_name}.pdf",
            ".pdf",
            [("PDF", "*.pdf")],
        )
    except Exception as error:
        raise ValueError(
            "No se pudo abrir la ventana para guardar el PDF. Reinicia Agender y vuelve a intentarlo."
        ) from error
    if output is None:
        return {"ok": False, "canceled": True, "message": "Exportación cancelada."}

    resolved_height = max(REPORT_MIN_HEIGHT, min(int(page_height), 5000))
    document = _build_print_document(reports_html, resolved_height, assets_base_url)

    with tempfile.TemporaryDirectory(prefix="agender-wqreport-") as temporary:
        temporary_path = Path(temporary)
        html_path = temporary_path / "report.html"
        temporary_pdf = temporary_path / "report.pdf"
        html_path.write_text(document, encoding="utf-8")
        try:
            with chromium_browser() as browser:
                page = browser.new_page(
                    viewport={"width": REPORT_WIDTH, "height": resolved_height}
                )
                page.goto(html_path.as_uri(), wait_until="load", timeout=30_000)
                wait_for_images(page)
                page.pdf(
                    path=str(temporary_pdf),
                    width=f"{REPORT_WIDTH / CSS_PIXELS_PER_INCH}in",
                    height=f"{resolved_height / CSS_PIXELS_PER_INCH}in",
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
        except PlaywrightTimeoutError as error:
            raise ValueError(
                "El motor de exportación tardó demasiado en preparar el PDF."
            ) from error
        if not temporary_pdf.is_file() or temporary_pdf.stat().st_size == 0:
            raise ValueError("El motor de exportación no produjo un PDF válido.")
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(temporary_pdf, output)
        except OSError as error:
            raise ValueError(
                "No se pudo guardar el PDF en la ubicación seleccionada. Verifica los permisos y el espacio disponible."
            ) from error

    return {
        "ok": True,
        "canceled": False,
        "filePath": str(output),
        "message": "PDF exportado correctamente.",
    }


def _safe_file_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(value or "")).strip()
    return cleaned or "Reporte_CA"


def _sanitize_report_html(value: str) -> str:
    sanitized = re.sub(r"<\s*(script|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>", "", value, flags=re.I | re.S)
    sanitized = re.sub(r"<\s*(script|iframe|object|embed)\b[^>]*/?\s*>", "", sanitized, flags=re.I | re.S)
    return re.sub(r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", sanitized, flags=re.I)


def _build_print_document(reports_html: str, page_height: int, assets_base_url: str) -> str:
    app_css = REPORT_CSS.read_text(encoding="utf-8")
    safe_base = html.escape(assets_base_url, quote=True)
    safe_reports = _sanitize_report_html(reports_html)
    page_width_inches = REPORT_WIDTH / CSS_PIXELS_PER_INCH
    page_height_inches = page_height / CSS_PIXELS_PER_INCH
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <base href="{safe_base}">
  <style>{app_css}</style>
  <style>
    @page {{ size: {page_width_inches}in {page_height_inches}in; margin: 0; }}
    html, body {{
      margin: 0 !important; padding: 0 !important; width: {REPORT_WIDTH}px !important;
      background: #fff !important; overflow: visible !important;
      -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important;
    }}
    #reports {{
      display: block !important; width: {REPORT_WIDTH}px !important; height: auto !important;
      margin: 0 !important; padding: 0 !important; gap: 0 !important;
      transform: none !important; transform-origin: top left !important; background: #fff !important;
    }}
    #contextFormatMenu, .context-format-menu, .graph-image-upload-zone,
    .graph-image-context-menu, input[type="file"],
    .add-parameter-row-button, .remove-parameter-row-button {{ display: none !important; }}
    .report-page {{
      display: block !important; width: {REPORT_WIDTH}px !important; height: {page_height}px !important;
      min-height: {REPORT_MIN_HEIGHT}px !important; max-height: {page_height}px !important;
      margin: 0 !important; box-shadow: none !important; overflow: hidden !important;
      page-break-after: always !important; break-after: page !important;
      page-break-inside: avoid !important; break-inside: avoid !important;
      -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important;
    }}
    .report-page:last-child {{ page-break-after: auto !important; break-after: auto !important; }}
    .editable, .parameter-value, .editable-text-target, .graph-image {{ outline: none !important; }}
  </style>
</head>
<body>{safe_reports}</body>
</html>"""

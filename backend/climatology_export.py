from __future__ import annotations

import html
import re
import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .browser_render import chromium_browser
from .climatology import resolve_report_asset
from .desktop_dialogs import choose_save_file

PAGE_WIDTH = 1536
PAGE_HEIGHT = 1220
CSS_PIXELS_PER_INCH = 96
REPORT_LOGO = Path(__file__).resolve().parent.parent / "frontend" / "wqreport" / "img" / "logo.png"


def export_climatology_pdf(pages: list[dict[str, str]], suggested_name: str) -> dict[str, object]:
    if not pages:
        raise ValueError("Selecciona al menos un territorio para exportar.")
    resolved = [_resolve_page(item) for item in pages]
    try:
        output = choose_save_file(
            "Guardar seguimiento mensual del clima",
            f"{_safe_name(suggested_name)}.pdf",
            ".pdf",
            [("PDF", "*.pdf")],
        )
    except Exception as error:
        raise ValueError(
            "No se pudo abrir la ventana para guardar el PDF. Reinicia Agender y vuelve a intentarlo."
        ) from error
    if output is None:
        return {"ok": False, "canceled": True, "message": "Exportación cancelada."}

    with tempfile.TemporaryDirectory(prefix="agender-climatologia-") as temporary:
        temporary_path = Path(temporary)
        document = temporary_path / "reporte.html"
        pdf = temporary_path / "reporte.pdf"
        document.write_text(_document(resolved), encoding="utf-8")
        try:
            with chromium_browser() as browser:
                page = browser.new_page(viewport={"width": PAGE_WIDTH, "height": PAGE_HEIGHT})
                page.goto(document.as_uri(), wait_until="networkidle", timeout=30_000)
                page.wait_for_timeout(2_000)
                page.pdf(
                    path=str(pdf),
                    width=f"{PAGE_WIDTH / CSS_PIXELS_PER_INCH}in",
                    height=f"{PAGE_HEIGHT / CSS_PIXELS_PER_INCH}in",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
        except PlaywrightTimeoutError as error:
            raise ValueError("El motor de exportación tardó demasiado en preparar el PDF.") from error
        if not pdf.is_file() or pdf.stat().st_size == 0:
            raise ValueError("El motor de exportación no produjo un PDF válido.")
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pdf, output)
        except OSError as error:
            raise ValueError(
                "No se pudo guardar el PDF en la ubicación seleccionada. Verifica los permisos y el espacio disponible."
            ) from error
    return {"ok": True, "canceled": False, "filePath": str(output), "message": "PDF exportado correctamente."}


def _resolve_page(item: dict[str, str]) -> dict[str, str]:
    url = str(item.get("url") or "")
    match = re.fullmatch(r"/api/climatology/report-file/([a-f0-9]{32})/(.+)", url)
    if not match:
        raise ValueError("Uno de los reportes seleccionados no es válido.")
    report = resolve_report_asset(match.group(1), match.group(2))
    if report.suffix.lower() != ".html":
        raise ValueError("Solo se pueden exportar reportes HTML generados por Climatología.")
    return {**item, "file": report.as_uri()}


def _document(pages: list[dict[str, str]]) -> str:
    sections = []
    logo = REPORT_LOGO.as_uri() if REPORT_LOGO.is_file() else ""
    logo_html = (
        f'<img class="report-logo" src="{html.escape(logo, quote=True)}" alt="Alcaldía de Cuenca · ETAPA">'
        if logo
        else ""
    )
    for item in pages:
        territory = html.escape(item.get("territory", ""))
        station = html.escape(str(item.get("station", "")).replace("_", " "))
        period = html.escape(item.get("period", "").upper())
        kind = item.get("kind")
        title = "SEGUIMIENTO TÉRMICO" if kind == "temperature" else "SEGUIMIENTO DE PRECIPITACIONES"
        sections.append(
            f'<section class="page"><header><div class="heading"><h1>{title} <span>|</span> {period}</h1>'
            f"<p>SEGUIMIENTO MENSUAL DEL CLIMA EN LA {territory.upper()} · "
            f"ESTACIÓN DE REFERENCIA: {station}</p></div>{logo_html}"
            f'</header><iframe src="{html.escape(item["file"], quote=True)}"></iframe></section>'
        )
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><style>
@page {{ size: {PAGE_WIDTH / CSS_PIXELS_PER_INCH}in {PAGE_HEIGHT / CSS_PIXELS_PER_INCH}in; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: white; font-family: "Segoe UI", Arial, sans-serif; }}
.page {{
  width: {PAGE_WIDTH}px; height: {PAGE_HEIGHT}px; overflow: hidden;
  break-after: page; page-break-after: always; background: #f5f8fc; padding: 8px 16px 12px;
}}
.page:last-child {{ break-after: auto; page-break-after: auto; }}
header {{
  position: relative; height: 126px; display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); align-items: center; text-align: center;
  color: white; background: #073f63; border-bottom: 6px solid #54c8dd;
}}
.heading {{ grid-column: 2; grid-row: 1; padding: 0; }}
.report-logo {{
  grid-column: 1; grid-row: 1; justify-self: start; width: 340px; height: auto; margin-left: 4px;
  max-width: calc(100% - 12px); max-height: 100px; object-fit: contain;
}}
h1 {{ margin: 0; font-size: 37px; letter-spacing: .2px; }} h1 span {{ font-weight: 400; }}
p {{ margin: 10px 0 0; font-size: 16px; }}
iframe {{ display: block; width: 100%; height: calc(100% - 126px); border: 0; background: white; }}
</style></head><body>{"".join(sections)}</body></html>"""


def _safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(value or "")).strip()
    return cleaned or "Seguimiento_mensual_clima"

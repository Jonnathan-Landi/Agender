from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image

from .desktop_dialogs import choose_directory
from .wqreport_export import _find_edge

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_CSS = PROJECT_ROOT / "frontend" / "css" / "hydromet-report.css"
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


def export_hydromet_designs(
    reports: list[dict[str, Any]],
    report_date: date,
    report_time: str,
    assets_base_url: str,
) -> dict[str, object]:
    normalized = _validate_reports(reports)
    if not REPORT_CSS.is_file():
        raise ValueError("No se encontró la hoja de estilos del reporte hidrometeorológico.")
    edge = _find_edge()
    if edge is None:
        raise ValueError("No se encontró Microsoft Edge para generar las imágenes.")

    selected_root = choose_directory("Selecciona la carpeta para guardar los diseños")
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
            for index, report in enumerate(normalized):
                report_key = report["format"]
                document = _build_capture_document(
                    report["html"],
                    css,
                    assets_base_url,
                )
                html_path = temporary_path / f"{index:02d}-{report_key}.html"
                png_path = temporary_path / f"{index:02d}-{report_key}.png"
                profile_path = temporary_path / f"edge-profile-{index:02d}"
                html_path.write_text(document, encoding="utf-8")
                _capture_page(edge, html_path, png_path, profile_path)

                filename = f"{report_key}_{report_date.isoformat()}.jpg"
                _save_maximum_quality_jpeg(png_path, staging_folder / filename)
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
    assets_base_url: str,
) -> str:
    safe_base = html.escape(assets_base_url, quote=True)
    safe_report = _sanitize_report_html(report_html)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <base href="{safe_base}">
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
      background: #fff !important;
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
      background: #e9e9e9 !important;
    }}
    .hydromet-report-template {{
      width: {EXPORT_SIZE}px !important;
      height: {EXPORT_SIZE}px !important;
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


def _capture_page(
    edge: Path,
    html_path: Path,
    png_path: Path,
    profile_path: Path,
) -> None:
    command = [
        str(edge),
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw",
        "--force-device-scale-factor=1",
        "--virtual-time-budget=3000",
        f"--window-size={EXPORT_SIZE},{EXPORT_SIZE}",
        f"--user-data-dir={profile_path}",
        f"--screenshot={png_path}",
        html_path.as_uri(),
    ]
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=creation_flags,
        check=False,
    )
    if result.returncode != 0 or not png_path.is_file() or png_path.stat().st_size == 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ValueError(
            f"No se pudo capturar uno de los diseños.{f' {detail}' if detail else ''}"
        )


def _save_maximum_quality_jpeg(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, "#ffffff")
        flattened.paste(rgba, mask=rgba.getchannel("A"))
        flattened.save(
            destination,
            format="JPEG",
            quality=100,
            subsampling=0,
            optimize=True,
            dpi=(300, 300),
        )

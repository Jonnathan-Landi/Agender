from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from ..desktop_dialogs import choose_directory, choose_save_file


def safe_export_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "estacion"


def tabular_bytes(headers: list[str], rows: list[tuple[Any, ...]], delimiter: str) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def excel_bytes(headers: list[str], rows: list[tuple[Any, ...]]) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Datos")
    sheet.append([f"'{header}" if header.startswith(("=", "+", "-", "@")) else header for header in headers])
    for row in rows:
        sheet.append(list(row))
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def save_export_dialog(suggested_name: str, file_format: str) -> Path | None:
    file_types = {
        "dat": [("Archivo de datos", "*.dat")],
        "csv": [("Valores separados por comas", "*.csv")],
        "xlsx": [("Libro de Excel", "*.xlsx")],
    }
    return choose_save_file(
        title="Guardar datos hidrometeorológicos",
        suggested_name=suggested_name,
        default_extension=f".{file_format}",
        file_types=[*file_types[file_format], ("Todos los archivos", "*.*")],
    )


def choose_export_folder() -> Path | None:
    return choose_directory("Selecciona la carpeta para guardar las estaciones")


def unique_output_path(folder: Path, filename: str) -> Path:
    output = folder / filename
    if not output.exists():
        return output
    stem = output.stem
    for index in range(2, 10_000):
        candidate = folder / f"{stem} ({index}){output.suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError(f"No se pudo crear un nombre disponible para {filename}")

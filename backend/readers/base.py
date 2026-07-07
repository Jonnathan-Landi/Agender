from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import polars as pl

IDENTIFIER_COLUMNS = {"TIMESTAMP", "RECORD", "DATE", "DATETIME", "FECHA", "HORA"}
NULL_VALUES = ["", "NA", "N/A", "NaN", "nan", "null", "NULL"]


class DelimitedReader:
    source = "base"

    def read(self, file_path: Path, relative_path: str, fingerprint: dict[str, int]) -> dict[str, Any]:
        columns, separator = self._header(file_path)
        timestamp = self._timestamp_column(columns)
        variables = self.select_variables(columns)
        schema = {column: pl.String for column in columns}

        expressions: list[pl.Expr] = [pl.len().alias("__rows")]
        if timestamp:
            expressions.extend([
                pl.col(timestamp).min().alias("__start"),
                pl.col(timestamp).max().alias("__end"),
            ])
        for variable in variables:
            expressions.append(
                pl.col(variable).cast(pl.Float64, strict=False).is_not_null().sum().alias(variable)
            )

        frame = (
            pl.scan_csv(
                file_path,
                separator=separator,
                schema_overrides=schema,
                null_values=NULL_VALUES,
                ignore_errors=True,
                truncate_ragged_lines=True,
            )
            .select(expressions)
            .collect(engine="streaming")
        )
        summary = frame.row(0, named=True)
        row_count = int(summary.get("__rows") or 0)
        return {
            "relativePath": relative_path,
            "size": fingerprint["size"],
            "mtimeNs": fingerprint["mtimeNs"],
            "station": self.station_code(relative_path),
            "start": self._date_only(summary.get("__start")),
            "end": self._date_only(summary.get("__end")),
            "rows": row_count,
            "variables": {
                variable: {"valid": int(summary.get(variable) or 0), "expected": row_count}
                for variable in variables
            },
        }

    def select_variables(self, columns: list[str]) -> list[str]:
        return [column for column in columns if column.upper() not in IDENTIFIER_COLUMNS]

    @staticmethod
    def station_code(relative_path: str) -> str:
        return Path(relative_path).stem

    @staticmethod
    def _timestamp_column(columns: list[str]) -> str | None:
        preferred = ("TIMESTAMP", "DATETIME", "FECHA")
        by_upper = {column.upper(): column for column in columns}
        return next((by_upper[name] for name in preferred if name in by_upper), None)

    @staticmethod
    def _date_only(value: Any) -> str:
        text = str(value or "")
        return text[:10] if len(text) >= 10 else ""

    @staticmethod
    def _header(file_path: Path) -> tuple[list[str], str]:
        raw = file_path.read_bytes()[:64 * 1024]
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        first_line = text.splitlines()[0] if text.splitlines() else ""
        separator = "\t" if first_line.count("\t") > first_line.count(",") else ";" if first_line.count(";") > first_line.count(",") else ","
        columns = next(csv.reader([first_line], delimiter=separator), [])
        columns = [column.strip().strip('"') for column in columns]
        if not columns or any(not column for column in columns):
            raise ValueError("El archivo no tiene un encabezado válido.")
        return columns, separator

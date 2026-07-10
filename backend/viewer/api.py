from __future__ import annotations

import json
import os
import uuid
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

WORKER_THREADS = max(1, (os.cpu_count() or 2) - 2)
os.environ.setdefault("POLARS_MAX_THREADS", str(WORKER_THREADS))

import duckdb
import polars as pl
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel


from ..catalog import normalize_station_code
from ..config import APP_DATA_DIR, read_settings
from ..security import current_user


APP_ROOT = APP_DATA_DIR / "viewer"
CACHE_ROOT = APP_ROOT / "data" / "cache"
EXPORT_ROOT = APP_ROOT / "data" / "exports"

for directory in (CACHE_ROOT, EXPORT_ROOT):
    directory.mkdir(parents=True, exist_ok=True)


EXCLUDED_COLUMNS = {"record", "year", "id", "idx", "index", "row", "timestamp"}
MIN_REASONABLE_YEAR = 1990
MAX_REASONABLE_YEAR = datetime.now().year + 2
TIMESTAMP_CANDIDATES = (
    "timestamp",
    "tmstmp",
    "tmstamp",
    "timstamp",
    "datetime",
    "date_time",
    "fecha_hora",
    "fecha",
    "date",
    "ts",
)
WEAK_TIMESTAMP_CANDIDATES = ("time", "hora")
TIMESTAMP_ALIASES = {*TIMESTAMP_CANDIDATES, *WEAK_TIMESTAMP_CANDIDATES}
NUMERIC_DTYPES = {
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
    pl.Float64,
}


class SessionInfo(BaseModel):
    session_id: str
    filename: str
    timestamp_column: str
    variables: list[str]
    years: list[int]
    months_by_year: dict[str, list[int]]
    days_by_month: dict[str, list[int]]
    total_rows: int


app = FastAPI(title="Agender Viewer API", version="1.0.0")


def session_dir(session_id: str) -> Path:
    return CACHE_ROOT / session_id


def metadata_path(session_id: str) -> Path:
    return session_dir(session_id) / "metadata.json"


def parquet_path(session_id: str) -> Path:
    return session_dir(session_id) / "dataset.parquet"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def require_session(session_id: str) -> dict[str, Any]:
    path = metadata_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    return read_json(path, {})


def clean_name(name: str) -> str:
    cleaned = name.strip().strip('"').strip("'").lower()
    for char in (" ", "-", ".", "/", "\\", ":"):
        cleaned = cleaned.replace(char, "_")
    return cleaned


def canonical_name(name: str) -> str:
    return "".join(char for char in clean_name(name) if char.isalnum())


def is_timestamp_alias(name: str) -> bool:
    return canonical_name(name) in {canonical_name(alias) for alias in TIMESTAMP_ALIASES}


def is_strong_timestamp_alias(name: str) -> bool:
    return canonical_name(name) in {canonical_name(alias) for alias in TIMESTAMP_CANDIDATES}


def make_unique_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for index, column in enumerate(columns):
        base = column.strip().strip('"') or f"column_{index + 1}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        unique.append(base if count == 0 else f"{base}_{count + 1}")
    return unique


def detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def read_text_sample(path: Path, max_lines: int = 240) -> tuple[list[str], str]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            lines: list[str] = []
            with path.open("r", encoding=encoding, newline="") as fh:
                for _ in range(max_lines):
                    line = fh.readline()
                    if line == "":
                        break
                    lines.append(line.rstrip("\r\n"))
            return lines, encoding
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=422, detail="No se pudo leer el archivo de texto")


def row_has_parseable_timestamp(row: list[str], timestamp_index: int) -> bool:
    if timestamp_index >= len(row):
        return False
    return parse_timestamp_value(row[timestamp_index]) is not None


def count_metadata_rows_after_header(rows: list[list[str]], header_index: int, timestamp_index: int) -> int:
    metadata_rows = 0
    for row in rows[header_index + 1 : header_index + 9]:
        if row_has_parseable_timestamp(row, timestamp_index):
            break
        metadata_rows += 1
    return metadata_rows


def read_delimited_environmental_file(path: Path) -> pl.DataFrame:
    lines, encoding = read_text_sample(path)
    if not lines:
        raise HTTPException(status_code=422, detail="El archivo está vacío")

    sample = "\n".join(lines[:30])
    delimiter = detect_delimiter(sample)
    rows = list(csv.reader(lines, delimiter=delimiter))
    header_index = None

    for index, row in enumerate(rows[:200]):
        if row and is_timestamp_alias(row[0]):
            header_index = index
            break

    if header_index is None:
        for index, row in enumerate(rows[:200]):
            if any(is_timestamp_alias(cell) for cell in row):
                header_index = index
                break

    if header_index is None:
        return pl.read_csv(
            path,
            encoding=encoding,
            infer_schema_length=10000,
            try_parse_dates=True,
            ignore_errors=True,
        )

    header = make_unique_columns(rows[header_index])
    timestamp_index = next((index for index, cell in enumerate(rows[header_index]) if is_timestamp_alias(cell)), 0)
    metadata_rows = count_metadata_rows_after_header(rows, header_index, timestamp_index)

    try:
        df = pl.read_csv(
            path,
            encoding=encoding,
            separator=delimiter,
            has_header=True,
            skip_rows=header_index,
            skip_rows_after_header=metadata_rows,
            new_columns=header,
            infer_schema=False,
            ignore_errors=True,
            truncate_ragged_lines=True,
            null_values=["", "NA", "N/A", "NaN", "nan", "NULL", "null"],
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No se pudieron leer las columnas del archivo: {exc}") from exc

    if df.height == 0:
        raise HTTPException(status_code=422, detail="No se detectaron registros de datos")
    return df


def count_reasonable_datetimes(series: pl.Series) -> int:
    if series.is_empty():
        return 0
    try:
        years = series.dt.year()
    except Exception:
        return 0
    return int(years.filter((years >= MIN_REASONABLE_YEAR) & (years <= MAX_REASONABLE_YEAR)).drop_nulls().len())


def parsed_datetime_score(sample: pl.DataFrame, column: str) -> tuple[int, int]:
    try:
        parsed = sample.select(timestamp_parse_expr(column).alias("__candidate_timestamp")).to_series()
    except Exception:
        return (0, 0)
    parsed_non_null = parsed.drop_nulls()
    return (parsed_non_null.len(), count_reasonable_datetimes(parsed_non_null))


def detect_timestamp_column(df: pl.DataFrame) -> str:
    columns = list(df.columns)
    sample = df.head(min(5000, df.height))

    strong_aliases = [column for column in columns if is_strong_timestamp_alias(column)]
    weak_aliases = [column for column in columns if is_timestamp_alias(column) and column not in strong_aliases]
    for column in [*strong_aliases, *weak_aliases]:
        parsed_count, reasonable_count = parsed_datetime_score(sample, column)
        if reasonable_count > 0 or parsed_count >= max(1, min(sample.height, 50)):
            return column

    datetime_cols = [
        name for name, dtype in zip(df.columns, df.dtypes, strict=False) if dtype in (pl.Date, pl.Datetime, pl.Time)
    ]
    for column in datetime_cols:
        if df.schema[column] == pl.Time:
            continue
        values = sample[column].cast(pl.Datetime) if df.schema[column] == pl.Date else sample[column]
        if count_reasonable_datetimes(values.drop_nulls()) > 0:
            return column

    best_column = None
    best_score = (0, 0)
    for column in columns:
        score = parsed_datetime_score(sample, column)
        if score > best_score:
            best_column = column
            best_score = score

    if not best_column or best_score[0] == 0:
        raise HTTPException(status_code=422, detail="No timestamp column could be detected")
    return best_column


def normalize_timestamp(df: pl.DataFrame, timestamp_column: str) -> pl.DataFrame:
    dtype = df.schema[timestamp_column]
    if dtype == pl.Datetime:
        timestamp_expr = pl.col(timestamp_column)
    elif dtype == pl.Date:
        timestamp_expr = pl.col(timestamp_column).cast(pl.Datetime)
    else:
        timestamp_expr = timestamp_parse_expr(timestamp_column)

    normalized = df.with_columns(timestamp_expr.alias("__fd_timestamp"))
    normalized = normalized.filter(pl.col("__fd_timestamp").is_not_null())
    if normalized.height == 0 and dtype not in (pl.Datetime, pl.Date):
        parsed = parse_timestamp_series_python(df[timestamp_column])
        normalized = df.with_columns(parsed.alias("__fd_timestamp"))
        normalized = normalized.filter(pl.col("__fd_timestamp").is_not_null())
    if normalized.height:
        year_count = count_reasonable_datetimes(normalized["__fd_timestamp"].drop_nulls())
        if year_count == 0:
            raise HTTPException(
                status_code=422,
                detail=f"La columna {timestamp_column} no contiene fechas válidas para una serie temporal.",
            )
    return normalized.with_row_index("__fd_row_id")


def timestamp_parse_expr(column: str) -> pl.Expr:
    text = pl.col(column).cast(pl.Utf8).str.strip_chars().str.replace(r"(Z|[+-]\d{2}:?\d{2})$", "", literal=False)
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%.f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%.f",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d/%m/%y",
        "%m/%d/%y",
    ]
    return pl.coalesce([text.str.to_datetime(format=fmt, strict=False) for fmt in formats])


def parse_timestamp_value(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d/%m/%y",
        "%m/%d/%y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_timestamp_series_python(series: pl.Series) -> pl.Series:
    return pl.Series("__fd_timestamp", [parse_timestamp_value(value) for value in series], dtype=pl.Datetime)


def coerce_numeric_columns(df: pl.DataFrame, timestamp_column: str) -> pl.DataFrame:
    expressions = []
    excluded = {clean_name(timestamp_column), "__fd_row_id", "__fd_timestamp"}
    for column in df.columns:
        if clean_name(column) in excluded:
            continue
        if df.schema[column] in NUMERIC_DTYPES:
            continue

        numeric_expr = (
            pl.col(column)
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.replace(",", ".", literal=True)
            .cast(pl.Float64, strict=False)
        )
        parsed = df.select(numeric_expr.alias(column)).to_series()
        if parsed.drop_nulls().len() > 0:
            expressions.append(numeric_expr.alias(column))

    if not expressions:
        return df
    return df.with_columns(expressions)


def detect_variables(df: pl.DataFrame, timestamp_column: str) -> list[str]:
    excluded = {clean_name(timestamp_column), *EXCLUDED_COLUMNS, "__fd_row_id", "__fd_timestamp"}
    variables: list[str] = []
    for name, dtype in zip(df.columns, df.dtypes, strict=False):
        if clean_name(name) in excluded:
            continue
        if dtype in NUMERIC_DTYPES:
            variables.append(name)
    return variables


def infer_interval_microseconds(df: pl.DataFrame) -> int | None:
    if df.height < 2:
        return None
    delta = pl.col("__fd_timestamp").sort().cast(pl.Int64).diff().alias("delta")
    candidates = (
        df.select(delta)
        .filter(pl.col("delta") > 0)
        .group_by("delta")
        .len()
        .sort(["len", "delta"], descending=[True, False])
        .head(1)
    )
    if candidates.height == 0:
        return None
    interval = candidates["delta"][0]
    return int(interval) if interval and interval > 0 else None


def complete_time_series(df: pl.DataFrame) -> tuple[pl.DataFrame, int | None]:
    interval_us = infer_interval_microseconds(df)
    base = df.drop("__fd_row_id") if "__fd_row_id" in df.columns else df
    base = base.sort("__fd_timestamp")
    if not interval_us:
        return base.with_row_index("__fd_row_id"), None

    start, end = base.select(
        pl.col("__fd_timestamp").min().alias("start"),
        pl.col("__fd_timestamp").max().alias("end"),
    ).row(0)
    if start is None or end is None or start == end:
        return base.with_row_index("__fd_row_id"), interval_us

    value_columns = [column for column in base.columns if column != "__fd_timestamp"]
    deduplicated = base.group_by("__fd_timestamp", maintain_order=True).agg(
        [pl.col(column).first().alias(column) for column in value_columns]
    )
    timeline = pl.DataFrame(
        {
            "__fd_timestamp": pl.datetime_range(
                start,
                end,
                interval=f"{interval_us}us",
                eager=True,
            )
        }
    )
    completed = timeline.join(deduplicated, on="__fd_timestamp", how="left")
    return completed.with_row_index("__fd_row_id"), interval_us


def read_input_file(path: Path) -> pl.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt", ".dat"}:
        return read_delimited_environmental_file(path)
    if suffix == ".xlsx":
        return pl.read_excel(path)
    if suffix == ".parquet":
        return pl.read_parquet(path)
    raise HTTPException(status_code=415, detail=f"Unsupported file format: {suffix}")


def duckdb_query(session_id: str, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"PRAGMA threads={WORKER_THREADS}")
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def stats_payload(total: int, records: int) -> dict[str, Any]:
    missing = max(0, total - records)
    completeness = (records / total * 100) if total else 0.0
    return {
        "total": total,
        "records": records,
        "active": records,
        "missing": missing,
        "completeness": round(completeness, 2),
    }


RESOLUTION_INTERVALS = {
    "5min": ("5 minutes", 5 * 60 * 1_000_000),
    "hour": ("1 hour", 60 * 60 * 1_000_000),
    "day": ("1 day", 24 * 60 * 60 * 1_000_000),
    "month": ("1 month", None),
    "year": ("1 year", None),
}


def aggregation_function(variable: str) -> tuple[str, str]:
    """Devuelve la función SQL y su etiqueta según la convención de la variable."""
    canonical = clean_name(variable)
    if canonical.endswith("_min") or canonical == "min":
        return "MIN", "mínimo"
    if canonical.endswith("_max") or canonical == "max":
        return "MAX", "máximo"
    if any(token in canonical for token in ("lluvia", "precip", "rain", "ppt")):
        return "SUM", "suma"
    return "AVG", "promedio"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/stations/{station_code}", response_model=SessionInfo)
def open_station(station_code: str, request: Request, source: str = "raw") -> SessionInfo:
    """Abre el archivo más reciente asociado a una estación configurada."""
    if source not in {"raw", "quality"}:
        raise HTTPException(status_code=422, detail="Fuente no válida")
    user = current_user(request.cookies.get("agender_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")
    settings = read_settings(user["username"], user["role"] == "admin")
    root_value = settings["rawDataPath" if source == "raw" else "qualityDataPath"]
    recursive = settings["rawIncludeSubfolders" if source == "raw" else "qualityIncludeSubfolders"]
    if not root_value:
        raise HTTPException(status_code=404, detail="La ruta de datos no está configurada")
    root = Path(root_value).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="La ruta configurada no está disponible")

    normalized_code = normalize_station_code(station_code)
    candidates = root.rglob("*") if recursive else root.glob("*")
    matches = [
        path
        for path in candidates
        if path.is_file()
        and path.suffix.lower() in {".dat", ".csv", ".txt", ".xlsx", ".parquet"}
        and normalize_station_code(path.stem) == normalized_code
    ]
    if not matches:
        raise HTTPException(status_code=404, detail=f"No hay archivos para la estación {station_code}")
    selected = max(matches, key=lambda path: path.stat().st_mtime_ns)
    return ingest_file(selected, selected.name)


def ingest_file(source_path: Path, display_name: str) -> SessionInfo:
    """Convierte un archivo a una sesión Viewer sin alterar el original."""
    suffix = source_path.suffix.lower()
    if suffix not in {".dat", ".csv", ".txt", ".xlsx", ".parquet"}:
        raise HTTPException(status_code=415, detail="Formato no soportado")
    session_id = uuid.uuid4().hex
    session_dir(session_id).mkdir(parents=True, exist_ok=True)

    try:
        raw = read_input_file(source_path)
        timestamp_column = detect_timestamp_column(raw)
        normalized = normalize_timestamp(raw, timestamp_column)
        normalized = coerce_numeric_columns(normalized, timestamp_column)
        variables = detect_variables(normalized, timestamp_column)
        if not variables:
            raise HTTPException(status_code=422, detail="No se detectaron variables numéricas")
        normalized, interval_us = complete_time_series(normalized)

        normalized.write_parquet(parquet_path(session_id), compression="zstd")
        years = (
            normalized.select(pl.col("__fd_timestamp").dt.year().alias("year"))
            .drop_nulls()
            .unique()
            .sort("year")
            .to_series()
            .to_list()
        )
        period_rows = (
            normalized.select(
                pl.col("__fd_timestamp").dt.year().alias("year"),
                pl.col("__fd_timestamp").dt.month().alias("month"),
                pl.col("__fd_timestamp").dt.day().alias("day"),
            )
            .drop_nulls()
            .unique()
            .sort(["year", "month", "day"])
            .to_dicts()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {exc}") from exc

    months_by_year: dict[str, list[int]] = {}
    days_by_month: dict[str, list[int]] = {}
    for row in period_rows:
        year_key = str(int(row["year"]))
        month = int(row["month"])
        day = int(row["day"])
        month_key = f"{year_key}-{month:02d}"
        months_by_year.setdefault(year_key, [])
        if month not in months_by_year[year_key]:
            months_by_year[year_key].append(month)
        days_by_month.setdefault(month_key, [])
        if day not in days_by_month[month_key]:
            days_by_month[month_key].append(day)

    meta = {
        "session_id": session_id,
        "filename": display_name,
        "timestamp_column": timestamp_column,
        "variables": variables,
        "years": [int(year) for year in years],
        "months_by_year": months_by_year,
        "days_by_month": days_by_month,
        "total_rows": normalized.height,
        "sampling_interval_us": interval_us,
        "worker_threads": WORKER_THREADS,
        "source_path": str(source_path),
    }
    write_json(metadata_path(session_id), meta)
    return SessionInfo(**meta)


@app.get("/api/data")
def get_data(
    session_id: str,
    variable: str,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    resolution: str = "5min",
    min_coverage: float = 80.0,
) -> dict[str, Any]:
    meta = require_session(session_id)
    if variable not in meta["variables"]:
        raise HTTPException(status_code=404, detail="Variable not found")
    if day is not None and month is None:
        raise HTTPException(status_code=422, detail="Month is required when filtering by day")
    if resolution not in RESOLUTION_INTERVALS:
        raise HTTPException(status_code=422, detail="Resolución no válida")
    if not 0 < min_coverage <= 100:
        raise HTTPException(status_code=422, detail="La cobertura mínima debe estar entre 1 y 100")

    interval_label, fixed_resolution_us = RESOLUTION_INTERVALS[resolution]
    source_interval_us = meta.get("sampling_interval_us")
    if source_interval_us and fixed_resolution_us and fixed_resolution_us < source_interval_us:
        raise HTTPException(
            status_code=422,
            detail="La resolución elegida es menor que el intervalo original de los datos",
        )

    path = str(parquet_path(session_id)).replace("'", "''")
    var = variable.replace('"', '""')
    period_filters: list[str] = []
    params: list[Any] = []
    if year is not None:
        period_filters.append("year(__fd_timestamp) = ?")
        params.append(year)
    if month is not None:
        period_filters.append("month(__fd_timestamp) = ?")
        params.append(month)
    if day is not None:
        period_filters.append("day(__fd_timestamp) = ?")
        params.append(day)
    period_where_clause = " AND ".join(period_filters) if period_filters else "TRUE"

    stats_sql = f"""
        SELECT COUNT(*) AS total, COUNT("{var}") AS records
        FROM read_parquet('{path}')
        WHERE {period_where_clause}
    """
    total_expected, total_records = duckdb_query(session_id, stats_sql, params)[0]
    aggregate, aggregation_label = aggregation_function(variable)
    expected_sql = (
        f"GREATEST(1, ROUND((epoch(bucket + INTERVAL '{interval_label}') - epoch(bucket))"
        f" * 1000000 / {int(source_interval_us)}))"
        if source_interval_us
        else "GREATEST(1, available)"
    )
    data_sql = f"""
        WITH bucketed AS (
            SELECT
                time_bucket(INTERVAL '{interval_label}', __fd_timestamp) AS bucket,
                COUNT("{var}") AS available,
                {aggregate}("{var}") AS aggregated_value
            FROM read_parquet('{path}')
            WHERE {period_where_clause}
            GROUP BY bucket
        ), evaluated AS (
            SELECT
                bucket,
                available,
                {expected_sql} AS expected_count,
                aggregated_value
            FROM bucketed
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY bucket) - 1 AS row_id,
            bucket,
            CASE WHEN available * 100.0 / expected_count >= ? THEN aggregated_value ELSE NULL END AS value,
            ROUND(available * 100.0 / expected_count, 2) AS coverage,
            available,
            expected_count
        FROM evaluated
        ORDER BY bucket
    """
    rows = duckdb_query(session_id, data_sql, [*params, min_coverage])
    stats = stats_payload(int(total_expected), int(total_records))
    accepted_periods = sum(row[2] is not None for row in rows)
    return {
        "session_id": session_id,
        "variable": variable,
        "year": year,
        "month": month,
        "day": day,
        "resolution": resolution,
        "min_coverage": min_coverage,
        "aggregation": aggregation_label,
        "sampled": False,
        "stride": 1,
        "points_in_year": total_records,
        "points_in_period": total_records,
        "grouped_periods": len(rows),
        "accepted_periods": accepted_periods,
        "na_periods": len(rows) - accepted_periods,
        "row_ids": [int(row[0]) for row in rows],
        "x": [row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]) for row in rows],
        "y": [row[2] for row in rows],
        "coverage": [float(row[3]) for row in rows],
        "available": [int(row[4]) for row in rows],
        "expected": [int(row[5]) for row in rows],
        "stats": stats,
    }


@app.get("/api/stats")
def get_stats(session_id: str, variable: str) -> dict[str, Any]:
    meta = require_session(session_id)
    if variable not in meta["variables"]:
        raise HTTPException(status_code=404, detail="Variable not found")
    path = str(parquet_path(session_id)).replace("'", "''")
    var = variable.replace('"', '""')
    total, records = duckdb_query(
        session_id,
        f"SELECT COUNT(*), COUNT(\"{var}\") FROM read_parquet('{path}')",
    )[0]
    return stats_payload(int(total), int(records))


@app.post("/api/export")
def export_file(
    session_id: str = Form(...),
    format: str = Form("csv"),
) -> FileResponse:
    meta = require_session(session_id)
    fmt = format.lower()
    if fmt not in {"csv", "parquet"}:
        raise HTTPException(status_code=415, detail="Export format must be csv or parquet")

    df = pl.read_parquet(parquet_path(session_id))
    export_df = df.drop(["__fd_row_id", "__fd_timestamp"])
    stem = Path(meta["filename"]).stem
    output = EXPORT_ROOT / f"{stem}_QC.{fmt}"
    if fmt == "csv":
        export_df.write_csv(output, null_value="NA")
        media_type = "text/csv"
    else:
        export_df.write_parquet(output, compression="zstd")
        media_type = "application/octet-stream"

    return FileResponse(output, media_type=media_type, filename=output.name)

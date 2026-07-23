from __future__ import annotations

import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import duckdb
from fastapi import HTTPException

from .aggregations import RESOLUTION_INTERVALS, aggregation_function


class ExportQueryPayload(Protocol):
    variables: list[str]
    start_date: date | None
    end_date: date | None
    resolution: str
    min_coverage: float
    custom_value: int | None
    custom_unit: str | None


_duckdb_lock = threading.Lock()
_duckdb_connection: duckdb.DuckDBPyConnection | None = None


def execute_query(
    sql: str,
    params: list[Any] | None = None,
    worker_threads: int = 4,
) -> list[tuple[Any, ...]]:
    global _duckdb_connection
    with _duckdb_lock:
        if _duckdb_connection is None:
            _duckdb_connection = duckdb.connect(database=":memory:")
            _duckdb_connection.execute(f"PRAGMA threads={max(1, worker_threads)}")
        return _duckdb_connection.execute(sql, params or []).fetchall()


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def build_export_query(
    payload: ExportQueryPayload,
    meta: dict[str, Any],
    dataset_path: Path,
) -> tuple[str, list[Any], list[str]]:
    if not payload.variables:
        raise HTTPException(status_code=422, detail="Selecciona al menos una variable")
    unknown = [variable for variable in payload.variables if variable not in meta["variables"]]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Variables no disponibles: {', '.join(unknown)}")
    if payload.start_date and payload.end_date and payload.start_date > payload.end_date:
        raise HTTPException(status_code=422, detail="La fecha inicial no puede ser posterior a la fecha final")
    first_date = date.fromisoformat(meta["first_date"]) if meta.get("first_date") else None
    last_date = date.fromisoformat(meta["last_date"]) if meta.get("last_date") else None
    if first_date and payload.start_date and payload.start_date < first_date:
        raise HTTPException(
            status_code=422,
            detail=f"La fecha inicial está fuera del rango disponible ({first_date} a {last_date})",
        )
    if last_date and payload.end_date and payload.end_date > last_date:
        raise HTTPException(
            status_code=422,
            detail=f"La fecha final está fuera del rango disponible ({first_date} a {last_date})",
        )
    if payload.resolution not in {"original", "5min", "hour", "day", "month", "year", "custom"}:
        raise HTTPException(status_code=422, detail="Escala temporal no válida")
    if not 0 < payload.min_coverage <= 100:
        raise HTTPException(status_code=422, detail="La cobertura mínima debe estar entre 1 y 100")

    path = str(dataset_path).replace("'", "''")
    filters: list[str] = []
    filter_params: list[Any] = []
    if payload.start_date:
        filters.append("__fd_timestamp >= ?")
        filter_params.append(datetime.combine(payload.start_date, datetime.min.time()))
    if payload.end_date:
        filters.append("__fd_timestamp < ?")
        filter_params.append(datetime.combine(payload.end_date + timedelta(days=1), datetime.min.time()))
    where_clause = " AND ".join(filters) if filters else "TRUE"
    timestamp_label = meta.get("timestamp_column") or "fecha_hora"

    if payload.resolution == "original":
        columns = [_quoted_identifier(variable) for variable in payload.variables]
        sql = (
            f'SELECT __fd_timestamp AS {_quoted_identifier(timestamp_label)}, {", ".join(columns)} '
            f"FROM read_parquet('{path}') WHERE {where_clause} ORDER BY __fd_timestamp"
        )
        return sql, filter_params, [timestamp_label, *payload.variables]

    if payload.resolution == "custom":
        if payload.custom_value is None or not 1 <= payload.custom_value <= 10_000:
            raise HTTPException(status_code=422, detail="La resolución personalizada debe estar entre 1 y 10.000")
        custom_units = {
            "minute": ("minutes", 60 * 1_000_000),
            "hour": ("hours", 60 * 60 * 1_000_000),
            "day": ("days", 24 * 60 * 60 * 1_000_000),
        }
        if payload.custom_unit not in custom_units:
            raise HTTPException(status_code=422, detail="Unidad de resolución personalizada no válida")
        unit_label, unit_us = custom_units[payload.custom_unit]
        interval_label = f"{payload.custom_value} {unit_label}"
        fixed_resolution_us = payload.custom_value * unit_us
    else:
        interval_label, fixed_resolution_us = RESOLUTION_INTERVALS[payload.resolution]
    source_interval_us = meta.get("sampling_interval_us")
    if source_interval_us and fixed_resolution_us and fixed_resolution_us < source_interval_us:
        raise HTTPException(
            status_code=422,
            detail="La escala elegida es menor que el intervalo original de los datos",
        )
    bucket_sql = f"time_bucket(INTERVAL '{interval_label}', __fd_timestamp)"
    expected_sql = (
        f"GREATEST(1, ROUND((epoch({bucket_sql} + INTERVAL '{interval_label}') - epoch({bucket_sql}))"
        f" * 1000000 / {int(source_interval_us)}))"
        if source_interval_us
        else "1"
    )
    aggregates: list[str] = []
    coverage_params: list[Any] = []
    timestamp_header = (
        "TIMESTAMP"
        if payload.resolution in {"5min", "hour"}
        or (payload.resolution == "custom" and payload.custom_unit in {"minute", "hour"})
        else "Fecha"
    )
    output_columns = [timestamp_header]
    for variable in payload.variables:
        quoted = _quoted_identifier(variable)
        aggregate, _label = aggregation_function(variable)
        value_alias = _quoted_identifier(variable)
        aggregates.append(
            f"CASE WHEN COUNT({quoted}) * 100.0 / {expected_sql} >= ? "
            f"THEN {aggregate}({quoted}) ELSE NULL END AS {value_alias}"
        )
        coverage_params.append(payload.min_coverage)
        output_columns.append(variable)
    sql = f"""
        SELECT
            {bucket_sql} AS {_quoted_identifier(timestamp_header)},
            {", ".join(aggregates)}
        FROM read_parquet('{path}')
        WHERE {where_clause}
        GROUP BY 1
        ORDER BY 1
    """
    return sql, [*coverage_params, *filter_params], output_columns


def query_data(
    *,
    session_id: str,
    variable: str,
    year: int | None,
    month: int | None,
    day: int | None,
    resolution: str,
    min_coverage: float,
    meta: dict[str, Any],
    dataset_path: Path,
    worker_threads: int,
) -> dict[str, Any]:
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

    path = str(dataset_path).replace("'", "''")
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
    total_expected, total_records = execute_query(stats_sql, params, worker_threads)[0]
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
    rows = execute_query(data_sql, [*params, min_coverage], worker_threads)
    missing_ranges: list[dict[str, Any]] = []
    if source_interval_us:
        gaps_sql = f"""
            WITH ordered AS (
                SELECT
                    __fd_timestamp,
                    LAG(__fd_timestamp) OVER (ORDER BY __fd_timestamp) AS previous_timestamp
                FROM read_parquet('{path}')
                WHERE {period_where_clause}
            )
            SELECT
                previous_timestamp + INTERVAL '{int(source_interval_us)} microseconds' AS gap_start,
                __fd_timestamp - INTERVAL '{int(source_interval_us)} microseconds' AS gap_end,
                CAST(ROUND(
                    (epoch(__fd_timestamp) - epoch(previous_timestamp)) * 1000000
                    / {int(source_interval_us)}
                ) - 1 AS BIGINT) AS missing_count
            FROM ordered
            WHERE previous_timestamp IS NOT NULL
              AND epoch(__fd_timestamp) - epoch(previous_timestamp) > {int(source_interval_us)} / 1000000.0
            ORDER BY gap_start
        """
        gap_rows = execute_query(gaps_sql, params, worker_threads)
        missing_ranges = [
            {
                "start": row[0].isoformat(),
                "end": row[1].isoformat(),
                "count": int(row[2]),
            }
            for row in gap_rows
        ]
    stats = _stats_payload(int(total_expected), int(total_records))
    missing_points = sum(gap["count"] for gap in missing_ranges)
    if missing_points:
        stats["total"] += missing_points
        stats["missing"] += missing_points
        stats["completeness"] = round(stats["records"] / stats["total"] * 100, 2)
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
        "missing_ranges": missing_ranges,
        "missing_points": missing_points,
        "stats": stats,
    }


def _stats_payload(total: int, records: int) -> dict[str, Any]:
    missing = max(0, total - records)
    completeness = (records / total * 100) if total else 0.0
    return {
        "total": total,
        "records": records,
        "active": records,
        "missing": missing,
        "completeness": round(completeness, 2),
    }

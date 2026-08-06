from __future__ import annotations

import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from calendar import monthrange
from pathlib import Path
from typing import Any

import polars as pl

from .catalog import load_station_catalog
from .climatology_renderer import render_rain, render_temperature
from .config import APP_DATA_DIR

CLIMATOLOGY_REPORT_ROOT = APP_DATA_DIR / "reports" / "climatology"


CLIMATE_AREAS = (
    ("urban", "Zona urbana", "Cuenca"),
    ("yanuncay", "Cuenca del Yanuncay", "Yanuncay"),
    ("tomebamba", "Cuenca del Tomebamba", "Tomebamba"),
    ("tarqui", "Cuenca del Tarqui", "Tarqui"),
    ("machangara", "Cuenca del Machángara", "Machangara"),
)


def station_configuration_catalog() -> dict[str, object]:
    stations = load_station_catalog().values()
    areas: list[dict[str, Any]] = []
    for area_id, label, catalog_basin in CLIMATE_AREAS:
        basin_stations = [station for station in stations if station["basin"] == catalog_basin]
        areas.append(
            {
                "id": area_id,
                "label": label,
                "catalogBasin": catalog_basin,
                "temperatureStations": _options(basin_stations, "temperature"),
                "rainStations": _options(basin_stations, "rain"),
            }
        )
    return {"areas": areas}


def build_exact_monthly_report(
    data_root: str, recursive: bool, year: int, month: int, selections: dict[str, dict[str, str]]
) -> dict[str, object]:
    root = Path(data_root).resolve()
    if not root.is_dir():
        raise ValueError("La carpeta de datos procesados no está disponible.")
    job_id = uuid.uuid4().hex
    job_root = CLIMATOLOGY_REPORT_ROOT / job_id
    job_root.mkdir(parents=True, exist_ok=False)
    catalog = load_station_catalog()
    results: dict[tuple[str, str], dict[str, str]] = {}
    tasks = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        for area_id, _label, basin in CLIMATE_AREAS:
            selected = selections.get(area_id, {})
            for kind in ("temperature", "rain"):
                code = str(selected.get(kind, "")).strip()
                validation = _validate_selection(catalog, basin, kind, code)
                if validation:
                    results[(area_id, kind)] = {"station": code, "error": validation}
                    continue
                path = _find_station_file(root, code, recursive)
                if not path:
                    results[(area_id, kind)] = {
                        "station": code,
                        "error": "No se encontró el archivo procesado de la estación.",
                    }
                    continue
                output = job_root / area_id / kind
                output.mkdir(parents=True, exist_ok=True)
                future = executor.submit(_run_python_report, kind, path, code, year, month, output)
                tasks.append((future, area_id, kind, code, output))
        for future, area_id, kind, code, output in tasks:
            try:
                report_path = future.result()
                relative = report_path.relative_to(output).as_posix()
                results[(area_id, kind)] = {
                    "station": code,
                    "url": f"/api/climatology/report-file/{job_id}/{area_id}/{kind}/{relative}",
                }
            # A malformed station file must not turn the complete batch into a
            # plain-text HTTP 500. Keep failures scoped to the station, just as
            # validation and missing-file errors are scoped above.
            except Exception as error:
                results[(area_id, kind)] = {"station": code, "error": str(error)}
    return {
        "jobId": job_id,
        "year": year,
        "month": month,
        "areas": [
            {
                "id": area_id,
                "label": label,
                "temperature": results[(area_id, "temperature")],
                "rain": results[(area_id, "rain")],
            }
            for area_id, label, _basin in CLIMATE_AREAS
        ],
    }


def resolve_report_asset(job_id: str, asset_path: str) -> Path:
    if not job_id.isalnum() or len(job_id) != 32:
        raise ValueError("Reporte no válido.")
    root = (CLIMATOLOGY_REPORT_ROOT / job_id).resolve()
    target = (root / asset_path).resolve()
    if root not in target.parents or not target.is_file():
        raise ValueError("Archivo de reporte no encontrado.")
    return target


def _validate_selection(catalog: dict[str, dict[str, Any]], basin: str, kind: str, code: str) -> str:
    if not code:
        return "Selecciona una estación en Configuración."
    station = next((item for item in catalog.values() if item["code"] == code), None)
    if not station or station["basin"] != basin or not _supports(station["type"], kind):
        return "La estación seleccionada no corresponde a este territorio."
    return ""


def _run_python_report(kind: str, data_file: Path, station: str, year: int, month: int, output: Path) -> Path:
    if kind == "temperature":
        report = _temperature_report(data_file, station.replace("_", " "), year, month)
        return render_temperature(report, output, year, month)
    report = _rain_report(data_file, station.replace("_", " "), year, month)
    return render_rain(report, output, year, month)


def _options(stations: list[dict[str, Any]], capability: str) -> list[dict[str, Any]]:
    return [
        {
            "code": station["code"],
            "type": station["type"],
            "altitude": station["z"],
        }
        for station in sorted(stations, key=lambda item: item["code"].casefold())
        if _supports(station["type"], capability)
    ]


def _supports(station_type: str, capability: str) -> bool:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", station_type).casefold()
        if not unicodedata.combining(character)
    )
    if capability == "temperature":
        return "meteorologica" in normalized
    if capability == "rain":
        return "meteorologica" in normalized or "pluviografica" in normalized
    return False


def _find_station_file(root: Path, code: str, recursive: bool) -> Path | None:
    patterns = tuple(f"{code}{suffix}" for suffix in (".dat", ".csv", ".txt"))
    for name in patterns:
        direct = root / name
        if direct.is_file():
            return direct
    if recursive:
        names = {name.casefold() for name in patterns}
        return next((path for path in root.rglob("*") if path.is_file() and path.name.casefold() in names), None)
    return None


def _read_columns(path: Path, columns: list[str]) -> pl.DataFrame:
    header = path.read_bytes()[:65536].decode("utf-8-sig", errors="replace").splitlines()[0]
    separator = (
        "\t" if header.count("\t") > header.count(",") else ";" if header.count(";") > header.count(",") else ","
    )
    available = {item.strip().strip('"') for item in header.split(separator)}
    missing = [column for column in columns if column not in available]
    if missing:
        raise ValueError(f"Faltan variables requeridas: {', '.join(missing)}.")
    schema_overrides = {column: pl.String if column == "TIMESTAMP" else pl.Float64 for column in columns}
    frame = pl.read_csv(
        path,
        separator=separator,
        columns=columns,
        schema_overrides=schema_overrides,
        null_values=["", "NA", "N/A", "NaN", "nan", "null", "NULL"],
        ignore_errors=True,
        try_parse_dates=False,
    )
    return frame.with_columns(
        pl.col("TIMESTAMP").cast(pl.String).str.to_datetime(strict=False, time_zone="UTC").alias("timestamp")
    ).filter(pl.col("timestamp").is_not_null())


def _temperature_report(path: Path, code: str, year: int, month: int) -> dict[str, object]:
    frame = _read_columns(path, ["TIMESTAMP", "TempAire_Min", "TempAire_Avg", "TempAire_Max"])
    daily = (
        frame.with_columns(
            pl.col("timestamp").dt.date().alias("date"),
            pl.col("TempAire_Min").cast(pl.Float64, strict=False),
            pl.col("TempAire_Avg").cast(pl.Float64, strict=False),
            pl.col("TempAire_Max").cast(pl.Float64, strict=False),
        )
        .group_by("date")
        .agg(
            pl.col("TempAire_Avg").count().alias("count"),
            pl.col("TempAire_Min").min().alias("minimum"),
            pl.col("TempAire_Avg").mean().alias("mean"),
            pl.col("TempAire_Max").max().alias("maximum"),
        )
        .with_columns(pl.col("date").dt.year().alias("year"), pl.col("date").dt.month().alias("month"))
        .filter(pl.col("count") >= 288 * 0.8)
        .sort("date")
    )
    target = daily.filter((pl.col("year") == year) & (pl.col("month") == month))
    if target.is_empty():
        raise ValueError("No existen días válidos para el periodo seleccionado.")
    rows = target.select("date", "minimum", "mean", "maximum").to_dicts()
    monthly = (
        daily.filter((pl.col("year") == year) & (pl.col("month") <= month))
        .group_by("month")
        .agg(
            pl.col("mean").mean().alias("value"),
            pl.col("minimum").min().alias("minimum"),
            pl.col("maximum").max().alias("maximum"),
        )
        .sort("month")
        .to_dicts()
    )
    historical = (
        daily.filter((pl.col("year") < year) & (pl.col("month") == month))
        .with_columns(pl.col("date").dt.day().alias("day"))
        .group_by("day")
        .agg(
            pl.col("minimum").mean().alias("minimumMean"),
            pl.col("minimum").quantile(0.1).alias("minimumP10"),
            pl.col("minimum").quantile(0.9).alias("minimumP90"),
            pl.col("maximum").mean().alias("maximumMean"),
            pl.col("maximum").quantile(0.1).alias("maximumP10"),
            pl.col("maximum").quantile(0.9).alias("maximumP90"),
        )
        .sort("day")
        .to_dicts()
    )
    historical_by_day = {row["day"]: row for row in historical}
    comparable_days = []
    for row in target.iter_rows(named=True):
        reference = historical_by_day.get(row["date"].day)
        required = (
            row["minimum"],
            row["maximum"],
            reference.get("minimumP10") if reference else None,
            reference.get("minimumP90") if reference else None,
            reference.get("maximumP10") if reference else None,
            reference.get("maximumP90") if reference else None,
        )
        if all(value is not None for value in required):
            comparable_days.append((row, reference))
    hot_days = sum(row["maximum"] > reference["maximumP90"] for row, reference in comparable_days)
    cold_days = sum(row["minimum"] < reference["minimumP10"] for row, reference in comparable_days)
    within_days = sum(
        reference["minimumP10"] <= row["minimum"] <= reference["minimumP90"]
        and reference["maximumP10"] <= row["maximum"] <= reference["maximumP90"]
        for row, reference in comparable_days
    )
    hottest = target.sort("maximum", descending=True).row(0, named=True)
    hottest_record = (
        frame.with_columns(
            pl.col("timestamp").dt.date().alias("date"),
            pl.col("timestamp").dt.strftime("%H:%M").alias("time"),
            pl.col("TempAire_Max").cast(pl.Float64, strict=False).alias("value"),
        )
        .filter(pl.col("date") == hottest["date"])
        .select("time", "value")
        .drop_nulls("value")
        .sort("value", descending=True)
        .row(0, named=True)
    )
    hottest_detail = (
        frame.with_columns(
            pl.col("timestamp").dt.date().alias("date"),
            pl.col("timestamp").dt.strftime("%H:%M").alias("time"),
            pl.col("TempAire_Avg").cast(pl.Float64, strict=False).alias("value"),
        )
        .filter(pl.col("date") == hottest["date"])
        .select("time", "value")
        .drop_nulls("value")
        .to_dicts()
    )
    previous_values = [row["value"] for row in monthly if row["month"] < month and row["value"] is not None]
    current_mean = target["mean"].mean()
    previous_mean = sum(previous_values) / len(previous_values) if previous_values else None
    current_month = next(row for row in monthly if row["month"] == month)
    other_months = [row for row in monthly if row["month"] < month]
    other_maxima = [row["maximum"] for row in other_months if row["maximum"] is not None]
    other_minima = [row["minimum"] for row in other_months if row["minimum"] is not None]
    maximum_reference = sum(other_maxima) / len(other_maxima) if other_maxima else None
    minimum_reference = sum(other_minima) / len(other_minima) if other_minima else None
    ranks = sorted(row["value"] for row in monthly if row["value"] is not None)
    historical_years = daily.filter((pl.col("year") < year) & (pl.col("month") == month))["year"].unique().to_list()
    return {
        "station": code,
        "summary": {
            "minimum": target["minimum"].min(),
            "mean": target["mean"].mean(),
            "maximum": target["maximum"].max(),
            "validDays": target.height,
            "expectedDays": monthrange(year, month)[1],
            "rank": ranks.index(min(ranks, key=lambda value: abs(value - current_mean))) + 1 if ranks else 1,
            "rankTotal": len(ranks),
            "previousDifference": current_mean - previous_mean if previous_mean is not None else None,
            "monthlyMaximumDifference": (
                current_month["maximum"] - maximum_reference if maximum_reference is not None else None
            ),
            "monthlyMinimumDifference": (
                current_month["minimum"] - minimum_reference if minimum_reference is not None else None
            ),
            "hottestDate": hottest["date"].isoformat(),
            "hottestMaximum": hottest["maximum"],
            "hottestTime": hottest_record["time"],
            "historicalPeriod": _period(historical_years),
            "historicalComparableDays": len(comparable_days),
            "historicalHotDays": hot_days,
            "historicalColdDays": cold_days,
            "historicalWithinDays": within_days,
            "historicalThroughDay": target["date"].max().day,
            "reportDate": target["date"].max().isoformat(),
        },
        "daily": [{**row, "date": row["date"].isoformat()} for row in rows],
        "monthly": monthly,
        "historical": historical,
        "hottest": hottest_detail,
    }


def _rain_report(path: Path, code: str, year: int, month: int) -> dict[str, object]:
    frame = _read_columns(path, ["TIMESTAMP", "Lluvia_Tot"])
    daily = (
        frame.with_columns(
            pl.col("timestamp").dt.date().alias("date"),
            pl.col("Lluvia_Tot").cast(pl.Float64, strict=False).clip(lower_bound=0).alias("rain"),
        )
        .group_by("date")
        .agg(pl.col("rain").count().alias("count"), pl.col("rain").sum().alias("rain"))
        .with_columns(pl.col("date").dt.year().alias("year"), pl.col("date").dt.month().alias("month"))
        .filter(pl.col("count") >= 288 * 0.8)
        .sort("date")
    )
    target = daily.filter((pl.col("year") == year) & (pl.col("month") == month))
    if target.is_empty():
        raise ValueError("No existen días válidos para el periodo seleccionado.")
    rows = target.select("date", "rain").to_dicts()
    total = target["rain"].sum()
    wettest = target.sort("rain", descending=True).row(0, named=True)
    monthly = (
        daily.group_by("year", "month")
        .agg(pl.col("rain").sum().alias("value"), pl.len().alias("validDays"))
        .sort("year", "month")
    )
    current_monthly = monthly.filter((pl.col("year") == year) & (pl.col("month") <= month)).sort("month")
    historical_cumulative = (
        monthly.filter(pl.col("year") < year)
        .sort("year", "month")
        .with_columns(pl.col("value").cum_sum().over("year").alias("cumulative"))
        .group_by("month")
        .agg(
            pl.col("cumulative").mean().alias("mean"),
            pl.col("cumulative").quantile(0.1).alias("p10"),
            pl.col("cumulative").quantile(0.9).alias("p90"),
        )
        .sort("month")
    )
    current_rows = current_monthly.select("month", "value").to_dicts()
    historical_rows = historical_cumulative.to_dicts()
    running = 0.0
    for row in current_rows:
        running += row["value"] or 0
        row["cumulative"] = running
    current_to_date = next((row["cumulative"] for row in current_rows if row["month"] == month), total)
    historical_to_date = next((row["mean"] for row in historical_rows if row["month"] == month), None)
    historical_target = monthly.filter(
        (pl.col("year") < year) & (pl.col("month") == month) & (pl.col("validDays") >= monthrange(year, month)[1] * 0.8)
    )
    historical_mean = historical_target["value"].mean() if not historical_target.is_empty() else None
    difference = total - historical_mean if historical_mean is not None else None
    history = historical_target.select("year", "value").sort("year").to_dicts()
    history_values = sorted(row["value"] for row in history)
    rank_values = sorted(current_monthly["value"].to_list(), reverse=True)
    daily_history = (
        daily.filter((pl.col("year") < year) & (pl.col("month") == month))
        .with_columns(pl.col("date").dt.day().alias("day"))
        .group_by("day")
        .agg(
            pl.col("rain").mean().alias("mean"),
            pl.col("rain").quantile(0.1).alias("p10"),
            pl.col("rain").quantile(0.9).alias("p90"),
        )
        .sort("day")
        .to_dicts()
    )
    return {
        "station": code,
        "summary": {
            "total": total,
            "rainDays": target.filter(pl.col("rain") >= 0.1).height,
            "maximum": wettest["rain"],
            "maximumDate": wettest["date"].isoformat(),
            "validDays": target.height,
            "expectedDays": monthrange(year, month)[1],
            "historicalMean": historical_mean,
            "difference": difference,
            "differencePercent": difference / historical_mean * 100 if historical_mean else None,
            "rank": rank_values.index(total) + 1 if total in rank_values else 1,
            "rankTotal": len(rank_values),
            "historicalPeriod": _period(historical_target["year"].to_list()),
            "historyMean": sum(history_values) / len(history_values) if history_values else None,
            "annualTotal": current_to_date,
            "annualHistoricalMean": historical_to_date,
            "reportDate": target["date"].max().isoformat(),
        },
        "daily": [{**row, "date": row["date"].isoformat()} for row in rows],
        "dailyHistorical": daily_history,
        "monthly": current_rows,
        "monthlyHistorical": historical_rows,
        "history": history,
    }


def _period(years: list[int]) -> str:
    return f"{min(years)}-{max(years)}" if years else "Sin histórico"

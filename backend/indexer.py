from __future__ import annotations

import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .catalog import load_station_catalog, normalize_station_code
from .config import CACHE_DIR, read_json, write_json_atomic
from .readers import QualityReader, RawReader

DATA_EXTENSIONS = {".csv", ".dat", ".txt"}
CACHE_VERSION = 1
_locks = {"raw": threading.Lock(), "quality": threading.Lock()}


def synchronize(source: str, root_value: str, recursive: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    if source not in _locks:
        raise ValueError("La fuente seleccionada no es válida.")
    catalog = load_station_catalog()
    if not root_value:
        return _empty_result(source, "La ruta seleccionada no está configurada.", started, catalog)
    root = Path(root_value).resolve()
    if not root.is_dir():
        return _empty_result(source, f"No se pudo leer la carpeta {root}.", started, catalog)

    with _locks[source]:
        cache_path = CACHE_DIR / f"inventory_{source}.json"
        cached = read_json(cache_path, {})
        cache_matches = (
            cached.get("version") == CACHE_VERSION
            and cached.get("root") == str(root)
            and cached.get("recursive", True) == recursive
        )
        old_entries = cached.get("files", {}) if cache_matches else {}
        files = _discover(root, recursive)
        entries: dict[str, Any] = {}
        warnings: list[str] = []
        processed = 0
        reused = 0
        reader = RawReader() if source == "raw" else QualityReader()
        eligible_files = []
        for relative, file_path, fingerprint in files:
            metadata = catalog.get(normalize_station_code(reader.station_code(relative)))
            if metadata:
                eligible_files.append((relative, file_path, fingerprint, metadata))
        ignored = len(files) - len(eligible_files)
        current_keys = {relative for relative, _, _, _ in eligible_files}

        for relative, file_path, fingerprint, metadata in eligible_files:
            cached_entry = old_entries.get(relative)
            if (
                cached_entry
                and cached_entry.get("size") == fingerprint["size"]
                and cached_entry.get("mtimeNs") == fingerprint["mtimeNs"]
            ):
                cached_entry["station"] = metadata["code"]
                entries[relative] = cached_entry
                reused += 1
                continue
            try:
                entries[relative] = reader.read(file_path, relative, fingerprint)
                entries[relative]["station"] = metadata["code"]
                processed += 1
                _save_checkpoint(cache_path, source, root, recursive, entries)
            except Exception as error:
                warnings.append(f"No se pudo procesar {relative}: {error}")

        deleted = len(set(old_entries) - current_keys)
        _save_checkpoint(cache_path, source, root, recursive, entries)
        return {
            "data": _aggregate_stations(entries.values(), catalog),
            "source": source,
            "recursive": recursive,
            "fileCount": len(eligible_files),
            "ignoredFileCount": ignored,
            "catalogStationCount": len(catalog),
            "generatedAt": _iso_now(),
            "sync": {
                "processed": processed,
                "reused": reused,
                "deleted": deleted,
                "durationMs": round((time.perf_counter() - started) * 1000),
            },
            "warnings": warnings,
        }


def _discover(root: Path, recursive: bool) -> list[tuple[str, Path, dict[str, int]]]:
    result = []
    candidates = root.rglob("*") if recursive else root.glob("*")
    for file_path in candidates:
        if not file_path.is_file() or file_path.suffix.lower() not in DATA_EXTENSIONS:
            continue
        stat = file_path.stat()
        result.append(
            (file_path.relative_to(root).as_posix(), file_path, {"size": stat.st_size, "mtimeNs": stat.st_mtime_ns})
        )
    return result


def _save_checkpoint(cache_path: Path, source: str, root: Path, recursive: bool, entries: dict[str, Any]) -> None:
    write_json_atomic(
        cache_path,
        {
            "version": CACHE_VERSION,
            "source": source,
            "root": str(root),
            "recursive": recursive,
            "files": entries,
        },
    )


def _aggregate_stations(entries: Any, catalog: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    stations: dict[str, dict[str, Any]] = {
        metadata["code"]: {
            "dates": [],
            "variables": defaultdict(lambda: {"valid": 0, "expected": 0}),
            "files": 0,
        }
        for metadata in catalog.values()
    }
    for entry in entries:
        code = entry["station"]
        station = stations[code]
        station["files"] += 1
        station["dates"].extend(value for value in (entry.get("start"), entry.get("end")) if value)
        for variable, counts in entry.get("variables", {}).items():
            station["variables"][variable]["valid"] += counts["valid"]
            station["variables"][variable]["expected"] += counts["expected"]

    result = []
    for code, values in stations.items():
        metadata = catalog[normalize_station_code(code)]
        dates = sorted(values["dates"])
        completeness = {
            variable: min(100, counts["valid"] * 100 / counts["expected"])
            for variable, counts in values["variables"].items()
            if counts["expected"] > 0
        }
        result.append(
            {
                "code": metadata["code"],
                "type": metadata["type"],
                "x": metadata["x"],
                "y": metadata["y"],
                "z": metadata["z"],
                "basin": metadata["basin"],
                "start": dates[0] if dates else "",
                "end": dates[-1] if dates else "",
                "variables": sorted(values["variables"]),
                "completeness": completeness,
                "fileCount": values["files"],
            }
        )
    return sorted(result, key=lambda station: station["code"].casefold())


def _empty_result(source: str, warning: str, started: float, catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": _aggregate_stations([], catalog),
        "source": source,
        "fileCount": 0,
        "ignoredFileCount": 0,
        "catalogStationCount": len(catalog),
        "generatedAt": _iso_now(),
        "sync": {
            "processed": 0,
            "reused": 0,
            "deleted": 0,
            "durationMs": round((time.perf_counter() - started) * 1000),
        },
        "warnings": [warning],
    }


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()

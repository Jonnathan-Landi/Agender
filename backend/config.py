from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Any

APP_DATA_ROOT = Path(os.environ.get("APPDATA", Path.home()))
APP_DATA_DIR = APP_DATA_ROOT / "Agender"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"
CACHE_DIR = APP_DATA_DIR / "cache"

DEFAULT_SETTINGS = {
    "rawDataPath": "",
    "qualityDataPath": "",
    "rawIncludeSubfolders": True,
    "qualityIncludeSubfolders": True,
}


def user_settings_file(username: str | None = None, is_admin: bool = False) -> Path:
    if not username or is_admin:
        return SETTINGS_FILE
    identity = hashlib.sha256(username.strip().casefold().encode()).hexdigest()[:24]
    return APP_DATA_DIR / "users" / identity / "settings.json"


def read_settings(username: str | None = None, is_admin: bool = False) -> dict[str, Any]:
    path = user_settings_file(username, is_admin)
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return DEFAULT_SETTINGS.copy()
    return validate_settings(values)


def write_settings(values: dict[str, Any], username: str | None = None, is_admin: bool = False) -> dict[str, Any]:
    settings = validate_settings(values)
    _write_json_atomic(user_settings_file(username, is_admin), settings)
    return settings


def validate_settings(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise ValueError("Configuración no válida.")
    result: dict[str, Any] = {}
    for key, label in (("rawDataPath", "datos crudos"), ("qualityDataPath", "control de calidad")):
        value = values.get(key, "")
        if not isinstance(value, str) or "\0" in value or len(value) > 1024:
            raise ValueError(f"La ruta de {label} no es válida.")
        result[key] = value.strip()
    for key in ("rawIncludeSubfolders", "qualityIncludeSubfolders"):
        value = values.get(key, True)
        if not isinstance(value, bool):
            raise ValueError("La opción de incluir subcarpetas no es válida.")
        result[key] = value
    return result


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def write_json_atomic(path: Path, payload: Any) -> None:
    _write_json_atomic(path, payload)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)

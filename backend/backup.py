from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .config import read_settings, write_settings
from .user_data import DATA_MODULES, read_user_data, write_user_data

BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 12 * 1024 * 1024


def export_backup(user: dict[str, Any]) -> dict[str, Any]:
    is_admin = user["role"] == "admin"
    return {
        "format": "agender.backup",
        "version": BACKUP_VERSION,
        "exportedAt": datetime.now(UTC).isoformat(),
        "user": {
            "username": user["username"],
            "role": user["role"],
            "modules": user.get("modules", []),
        },
        "settings": read_settings(user["username"], is_admin),
        "data": read_user_data(user),
    }


def export_backup_bytes(user: dict[str, Any]) -> bytes:
    return json.dumps(export_backup(user), ensure_ascii=False, indent=2).encode("utf-8")


def import_backup_bytes(user: dict[str, Any], content: bytes) -> dict[str, Any]:
    if len(content) > MAX_BACKUP_BYTES:
        raise ValueError("El archivo de respaldo es demasiado grande.")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("El archivo no es un respaldo válido de Agender.") from error
    return import_backup(user, payload)


def import_backup(user: dict[str, Any], payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("format") != "agender.backup":
        raise ValueError("El archivo no es un respaldo válido de Agender.")
    if payload.get("version") != BACKUP_VERSION:
        raise ValueError("Esta versión de Agender no puede restaurar ese respaldo.")

    restored_settings = False
    settings = payload.get("settings")
    if isinstance(settings, dict):
        write_settings(settings, user["username"], user["role"] == "admin")
        restored_settings = True

    restored_data: list[str] = []
    data = payload.get("data")
    if isinstance(data, dict):
        modules = set(user.get("modules", []))
        allowed_keys = {key for key, module in DATA_MODULES.items() if module in modules}
        for key, value in data.items():
            if key not in allowed_keys:
                continue
            write_user_data(user, key, value)
            restored_data.append(key)

    return {
        "ok": True,
        "settings": restored_settings,
        "dataKeys": sorted(restored_data),
    }

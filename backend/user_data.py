from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .security import database

DATA_MODULES = {
    "agender.agenda.events": "agenda",
    "agender.diary.tasks": "diary",
    "agender.diary.focus": "diary",
    "agender.request.records": "requests",
    "agender.hydromet.qc-methods": "hydromet",
}
MAX_VALUE_BYTES = 5 * 1024 * 1024


def read_user_data(user: dict[str, Any]) -> dict[str, Any]:
    allowed = _allowed_keys(user)
    if not allowed:
        return {}
    placeholders = ",".join("?" for _ in allowed)
    with database() as connection:
        rows = connection.execute(
            f"SELECT data_key,value_json FROM user_data WHERE user_id=? AND data_key IN ({placeholders})",
            (user["id"], *allowed),
        ).fetchall()
    result: dict[str, Any] = {}
    for row in rows:
        try:
            result[row["data_key"]] = json.loads(row["value_json"])
        except json.JSONDecodeError:
            continue
    return result


def write_user_data(user: dict[str, Any], key: str, value: Any) -> None:
    if key not in _allowed_keys(user):
        raise PermissionError("No tienes acceso a este módulo.")
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ValueError("Los datos superan el límite permitido.")
    with database() as connection:
        connection.execute(
            """INSERT INTO user_data(user_id,data_key,value_json,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(user_id,data_key) DO UPDATE SET
            value_json=excluded.value_json,updated_at=excluded.updated_at""",
            (user["id"], key, serialized, datetime.now(UTC).isoformat()),
        )


def _allowed_keys(user: dict[str, Any]) -> tuple[str, ...]:
    modules = set(user.get("modules", []))
    return tuple(key for key, module in DATA_MODULES.items() if module in modules)

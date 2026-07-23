from __future__ import annotations

import json
import copy
from datetime import UTC, datetime
from typing import Any

from .security import database
from .sync_lock import user_sync_lock
from .portable_profile import MAX_PROFILE_BYTES, PROFILE_KEYS

DATA_MODULES = {
    "agender.profile.preferences": None,
    "agender.profile.onedrive-sources": None,
    "agender.agenda.events": "agenda",
    "agender.diary.tasks": "diary",
    "agender.diary.focus": "diary",
    "agender.request.records": "requests",
    "agender.hydromet.qc-methods": "hydromet",
    "agender.reports.water-quality": "report-water-quality",
    "agender.reports.water-quality.preferences": "report-water-quality",
}
LOCAL_ONLY_DATA_KEYS = {
    "agender.reports.water-quality",
    "agender.reports.water-quality.preferences",
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
    with user_sync_lock(int(user["id"])), database() as connection:
        previous_row = connection.execute(
            "SELECT value_json FROM user_data WHERE user_id=? AND data_key=?",
            (user["id"], key),
        ).fetchone()
        try:
            previous = json.loads(previous_row["value_json"]) if previous_row else None
        except json.JSONDecodeError:
            previous = None
        now = datetime.now(UTC).isoformat()
        normalized = _normalize_records(value, previous, now)
        serialized = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
        limit = MAX_PROFILE_BYTES if key in PROFILE_KEYS else MAX_VALUE_BYTES
        if len(serialized.encode("utf-8")) > limit:
            raise ValueError("Los datos superan el límite permitido.")
        _update_sync_metadata(connection, user["id"], key, previous, normalized, now)
        connection.execute(
            """INSERT INTO user_data(user_id,data_key,value_json,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(user_id,data_key) DO UPDATE SET
            value_json=excluded.value_json,updated_at=excluded.updated_at""",
            (user["id"], key, serialized, now),
        )


def _normalize_records(value: Any, previous: Any, now: str) -> Any:
    if not isinstance(value, list):
        return value
    old_by_id = {
        str(item["id"]): item
        for item in previous or []
        if isinstance(item, dict) and item.get("id") is not None
    }
    result: list[Any] = []
    for original in value:
        if not isinstance(original, dict) or original.get("id") is None:
            result.append(original)
            continue
        item = copy.deepcopy(original)
        record_id = str(item["id"])
        old = old_by_id.get(record_id)
        if not item.get("updatedAt"):
            if old and _without_timestamp(old) == _without_timestamp(item):
                item["updatedAt"] = old.get("updatedAt") or now
            else:
                item["updatedAt"] = now
        result.append(item)
    return result


def _without_timestamp(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "updatedAt"}


def _record_values(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        return {
            str(item["id"]): item
            for item in value
            if isinstance(item, dict) and item.get("id") is not None
        }
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return None


def _update_sync_metadata(
    connection: Any,
    user_id: int,
    key: str,
    previous: Any,
    current: Any,
    now: str,
) -> None:
    previous_records = _record_values(previous)
    current_records = _record_values(current)
    if previous_records is None or current_records is None:
        return
    previous_ids = set(previous_records)
    current_ids = set(current_records)
    for record_id in previous_ids - current_ids:
        connection.execute(
            """INSERT INTO sync_tombstones(user_id,data_key,record_id,deleted_at)
            VALUES(?,?,?,?) ON CONFLICT(user_id,data_key,record_id) DO UPDATE SET
            deleted_at=excluded.deleted_at""",
            (user_id, key, record_id, now),
        )
    for record_id in current_ids:
        old_value = previous_records.get(record_id)
        new_value = current_records[record_id]
        existing = connection.execute(
            "SELECT updated_at FROM sync_record_meta WHERE user_id=? AND data_key=? AND record_id=?",
            (user_id, key, record_id),
        ).fetchone()
        if old_value != new_value or not existing:
            item_timestamp = new_value.get("updatedAt") if isinstance(new_value, dict) else None
            connection.execute(
                """INSERT INTO sync_record_meta(user_id,data_key,record_id,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(user_id,data_key,record_id) DO UPDATE SET
                updated_at=excluded.updated_at""",
                (user_id, key, record_id, item_timestamp or now),
            )
        connection.execute(
            "DELETE FROM sync_tombstones WHERE user_id=? AND data_key=? AND record_id=?",
            (user_id, key, record_id),
        )


def _allowed_keys(user: dict[str, Any]) -> tuple[str, ...]:
    modules = set(user.get("modules", []))
    return tuple(key for key, module in DATA_MODULES.items() if module is None or module in modules)


def syncable_data_keys(user: dict[str, Any]) -> tuple[str, ...]:
    return tuple(key for key in _allowed_keys(user) if key not in LOCAL_ONLY_DATA_KEYS)

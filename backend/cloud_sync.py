from __future__ import annotations

import json
import hashlib
import secrets
import threading
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from .cloud_account import (
    CloudHttpError,
    _access_token,
    _bytes_request,
    _json_request,
    set_sync_result,
)
from .cloud_identity import cloud_profile_filename, cloud_profile_id
from .config import APP_DATA_DIR
from .security import database
from .sync_lock import user_sync_lock
from .portable_profile import PROFILE_SOURCES_KEY, apply_portable_onedrive_sources
from .user_data import syncable_data_keys

SYNC_FILE_PREFIX = "agender-sync-v1"
SYNC_FORMAT = "agender.sync"
SYNC_VERSION = 1
DEVICE_ID_FILE = APP_DATA_DIR / "device-id"
MAX_SYNC_ATTEMPTS = 4
_document_cache: dict[tuple[str, bytes], tuple[str, dict[str, Any]]] = {}
_document_cache_lock = threading.Lock()


def synchronize_onedrive(user: dict[str, Any]) -> dict[str, Any]:
    lock = user_sync_lock(int(user["id"]))
    if not lock.acquire(blocking=False):
        return {"ok": True, "busy": True, "remoteApplied": 0, "uploaded": False}
    try:
        result = _synchronize_locked(user)
        set_sync_result(user, result)
        return result
    except ValueError as error:
        set_sync_result(user, {"ok": False, "error": str(error)})
        raise
    finally:
        lock.release()


def _synchronize_locked(user: dict[str, Any]) -> dict[str, Any]:
    token = _access_token(user, "onedrive")
    device_id = _device_id()
    user_key = cloud_profile_id(user)
    file_name = cloud_profile_filename(SYNC_FILE_PREFIX, user)
    cache_key = _cache_key(token, file_name)
    conflicts = 0

    for _attempt in range(MAX_SYNC_ATTEMPTS):
        remote, etag, exists = _download_document(token, file_name)
        remote_user = remote.setdefault("users", {}).get(user_key, {"collections": {}})
        local_user = _local_document(user, device_id)
        merged_user, attempt_conflicts = _merge_user(local_user, remote_user)
        conflicts += attempt_conflicts
        needs_upload = not exists or merged_user != remote_user
        remote["users"][user_key] = merged_user
        remote.update({"format": SYNC_FORMAT, "version": SYNC_VERSION})

        if not needs_upload:
            remote_applied = _apply_merged_user(user, merged_user)
            now = datetime.now(UTC).isoformat()
            return {
                "ok": True,
                "busy": False,
                "uploaded": False,
                "remoteApplied": remote_applied,
                "conflicts": conflicts,
                "syncedAt": now,
                "modifiedAt": now,
            }

        content = json.dumps(remote, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            upload = _upload_document(token, file_name, content, etag, exists)
        except CloudHttpError as error:
            if error.code in {409, 412}:
                continue
            raise

        remote_applied = _apply_merged_user(user, merged_user)
        uploaded_etag = str(upload.get("eTag") or upload.get("etag") or "")
        if uploaded_etag:
            with _document_cache_lock:
                _document_cache[cache_key] = (uploaded_etag, deepcopy(remote))
        now = datetime.now(UTC).isoformat()
        return {
            "ok": True,
            "busy": False,
            "uploaded": True,
            "remoteApplied": remote_applied,
            "conflicts": conflicts,
            "syncedAt": now,
            "modifiedAt": upload.get("lastModifiedDateTime") or now,
        }
    raise ValueError("OneDrive cambió varias veces durante la sincronización. Intenta nuevamente.")


def _download_document(access_token: str, file_name: str) -> tuple[dict[str, Any], str, bool]:
    cache_key = _cache_key(access_token, file_name)
    base = f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/{file_name}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        metadata = _json_request(f"{base}?$select=id,eTag,lastModifiedDateTime", headers=headers)
    except CloudHttpError as error:
        if error.code == 404:
            with _document_cache_lock:
                _document_cache.pop(cache_key, None)
            return _empty_document(), "", False
        raise
    etag = str(metadata.get("eTag") or "")
    with _document_cache_lock:
        cached = _document_cache.get(cache_key)
        if cached and cached[0] == etag:
            return deepcopy(cached[1]), etag, True
    content = _bytes_request(f"{base}:/content", headers=headers)
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("El archivo de sincronización de OneDrive no es válido.") from error
    if not isinstance(document, dict) or document.get("format") != SYNC_FORMAT:
        raise ValueError("OneDrive contiene un archivo de sincronización incompatible.")
    if document.get("version") != SYNC_VERSION:
        raise ValueError("La versión del archivo de sincronización no es compatible.")
    document.setdefault("users", {})
    with _document_cache_lock:
        _document_cache[cache_key] = (etag, deepcopy(document))
    return document, etag, True


def _cache_key(access_token: str, file_name: str) -> tuple[str, bytes]:
    """Aísla la caché por cuenta sin conservar el token de acceso en memoria."""
    return file_name, hashlib.sha256(access_token.encode("utf-8")).digest()


def _upload_document(
    access_token: str,
    file_name: str,
    content: bytes,
    etag: str,
    exists: bool,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "If-Match" if exists else "If-None-Match": etag if exists else "*",
    }
    return _json_request(
        f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/{file_name}:/content",
        method="PUT",
        headers=headers,
        body=content,
    )


def _empty_document() -> dict[str, Any]:
    return {"format": SYNC_FORMAT, "version": SYNC_VERSION, "users": {}}


def _local_document(user: dict[str, Any], device_id: str) -> dict[str, Any]:
    allowed = set(syncable_data_keys(user))
    collections: dict[str, Any] = {}
    with database() as connection:
        rows = connection.execute(
            "SELECT data_key,value_json,updated_at FROM user_data WHERE user_id=?",
            (user["id"],),
        ).fetchall()
        tombstone_rows = connection.execute(
            "SELECT data_key,record_id,deleted_at,device_id FROM sync_tombstones WHERE user_id=?",
            (user["id"],),
        ).fetchall()
        meta_rows = connection.execute(
            "SELECT data_key,record_id,updated_at,device_id FROM sync_record_meta WHERE user_id=?",
            (user["id"],),
        ).fetchall()
    record_meta = {
        (row["data_key"], row["record_id"]): row
        for row in meta_rows
        if row["data_key"] in allowed
    }
    tombstones: dict[str, dict[str, Any]] = {}
    for row in tombstone_rows:
        if row["data_key"] not in allowed:
            continue
        tombstones.setdefault(row["data_key"], {})[row["record_id"]] = {
            "deletedAt": row["deleted_at"],
            "deviceId": row["device_id"] or device_id,
        }
    for row in rows:
        key = row["data_key"]
        if key not in allowed:
            continue
        try:
            value = json.loads(row["value_json"])
        except json.JSONDecodeError:
            continue
        records: dict[str, Any] = {}
        if isinstance(value, list):
            for index, item in enumerate(value):
                if not isinstance(item, dict) or item.get("id") is None:
                    continue
                meta = record_meta.get((key, str(item["id"])))
                records[str(item["id"])] = {
                    "updatedAt": item.get("updatedAt")
                    or (meta["updated_at"] if meta else None)
                    or row["updated_at"],
                    "deviceId": (meta["device_id"] if meta else "") or device_id,
                    "order": index,
                    "value": item,
                }
            kind = "list"
        elif isinstance(value, dict):
            for record_id, item in value.items():
                meta = record_meta.get((key, str(record_id)))
                records[str(record_id)] = {
                    "updatedAt": meta["updated_at"] if meta else row["updated_at"],
                    "deviceId": (meta["device_id"] if meta else "") or device_id,
                    "value": item,
                }
            kind = "map"
        else:
            records["__value__"] = {
                "updatedAt": row["updated_at"],
                "deviceId": device_id,
                "value": value,
            }
            kind = "value"
        records.update(tombstones.get(key, {}))
        collections[key] = {"records": records, "kind": kind}
    for key, records in tombstones.items():
        collections.setdefault(key, {"records": {}, "kind": "list"})["records"].update(records)
    return {"collections": collections}


def _merge_user(local: dict[str, Any], remote: Any) -> tuple[dict[str, Any], int]:
    remote = remote if isinstance(remote, dict) else {"collections": {}}
    merged = {"collections": {}}
    conflicts = 0
    keys = set(local.get("collections", {})) | set(remote.get("collections", {}))
    for key in keys:
        local_collection = local.get("collections", {}).get(key, {})
        remote_collection = remote.get("collections", {}).get(key, {})
        kind = local_collection.get("kind") or remote_collection.get("kind") or "list"
        records: dict[str, Any] = {}
        record_ids = set(local_collection.get("records", {})) | set(remote_collection.get("records", {}))
        for record_id in record_ids:
            local_record = local_collection.get("records", {}).get(record_id)
            remote_record = remote_collection.get("records", {}).get(record_id)
            winner, conflict = _merge_record(local_record, remote_record)
            if winner is not None:
                records[record_id] = winner
            conflicts += int(conflict)
        merged["collections"][key] = {"kind": kind, "records": records}
    return merged, conflicts


def _merge_record(local: Any, remote: Any) -> tuple[Any, bool]:
    if not isinstance(local, dict):
        return remote, False
    if not isinstance(remote, dict):
        return local, False
    local_time = str(local.get("deletedAt") or local.get("updatedAt") or "")
    remote_time = str(remote.get("deletedAt") or remote.get("updatedAt") or "")
    local_moment = _timestamp_value(local_time)
    remote_moment = _timestamp_value(remote_time)
    if local_moment != remote_moment:
        return (local if local_moment > remote_moment else remote), False
    if (
        local.get("value") == remote.get("value")
        and local.get("deletedAt") == remote.get("deletedAt")
    ):
        return remote, False
    local_canonical = json.dumps(local, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    remote_canonical = json.dumps(remote, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if local_canonical == remote_canonical:
        return local, False
    local_device = str(local.get("deviceId") or "")
    remote_device = str(remote.get("deviceId") or "")
    return (local if local_device >= remote_device else remote), True


def _timestamp_value(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _apply_merged_user(user: dict[str, Any], merged: dict[str, Any]) -> int:
    changed = 0
    portable_sources: Any = None
    with database() as connection:
        for key, collection in merged.get("collections", {}).items():
            if key not in syncable_data_keys(user):
                continue
            records = collection.get("records", {})
            kind = collection.get("kind")
            if kind == "value":
                envelope = records.get("__value__")
                if not isinstance(envelope, dict) or "value" not in envelope:
                    continue
                value = envelope["value"]
                updated_at = envelope.get("updatedAt") or datetime.now(UTC).isoformat()
            elif kind == "map":
                active_items = [
                    (record_id, envelope)
                    for record_id, envelope in records.items()
                    if isinstance(envelope, dict) and "value" in envelope and not envelope.get("deletedAt")
                ]
                value = {record_id: envelope["value"] for record_id, envelope in active_items}
                updated_at = max(
                    (str(item.get("updatedAt") or item.get("deletedAt") or "") for item in records.values()),
                    default=datetime.now(UTC).isoformat(),
                )
            else:
                active = [
                    envelope
                    for envelope in records.values()
                    if isinstance(envelope, dict) and "value" in envelope and not envelope.get("deletedAt")
                ]
                active.sort(key=lambda item: (int(item.get("order", 0)), str(item.get("updatedAt", ""))))
                value = [item["value"] for item in active]
                updated_at = max(
                    (str(item.get("updatedAt") or item.get("deletedAt") or "") for item in records.values()),
                    default=datetime.now(UTC).isoformat(),
                )
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            current = connection.execute(
                "SELECT value_json FROM user_data WHERE user_id=? AND data_key=?",
                (user["id"], key),
            ).fetchone()
            if not current or current["value_json"] != serialized:
                connection.execute(
                    """INSERT INTO user_data(user_id,data_key,value_json,updated_at) VALUES(?,?,?,?)
                    ON CONFLICT(user_id,data_key) DO UPDATE SET
                    value_json=excluded.value_json,updated_at=excluded.updated_at""",
                    (user["id"], key, serialized, updated_at),
                )
                changed += 1
            if key == PROFILE_SOURCES_KEY:
                portable_sources = value
            connection.execute(
                "DELETE FROM sync_tombstones WHERE user_id=? AND data_key=?",
                (user["id"], key),
            )
            connection.execute(
                "DELETE FROM sync_record_meta WHERE user_id=? AND data_key=?",
                (user["id"], key),
            )
            for record_id, envelope in records.items():
                if not isinstance(envelope, dict):
                    continue
                if envelope.get("deletedAt"):
                    connection.execute(
                        """INSERT INTO sync_tombstones(user_id,data_key,record_id,deleted_at,device_id)
                        VALUES(?,?,?,?,?) ON CONFLICT(user_id,data_key,record_id) DO UPDATE SET
                        deleted_at=excluded.deleted_at,device_id=excluded.device_id""",
                        (
                            user["id"],
                            key,
                            record_id,
                            envelope["deletedAt"],
                            envelope.get("deviceId") or "",
                        ),
                    )
                elif envelope.get("updatedAt"):
                    connection.execute(
                        """INSERT INTO sync_record_meta(user_id,data_key,record_id,updated_at,device_id)
                        VALUES(?,?,?,?,?) ON CONFLICT(user_id,data_key,record_id) DO UPDATE SET
                        updated_at=excluded.updated_at,device_id=excluded.device_id""",
                        (
                            user["id"],
                            key,
                            record_id,
                            envelope["updatedAt"],
                            envelope.get("deviceId") or "",
                        ),
                    )
    if portable_sources is not None and apply_portable_onedrive_sources(user, portable_sources):
        changed += 1
    return changed


def _device_id() -> str:
    try:
        value = DEVICE_ID_FILE.read_text(encoding="ascii").strip()
        if len(value) == 32:
            return value
    except OSError:
        pass
    value = secrets.token_hex(16)
    DEVICE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEVICE_ID_FILE.write_text(value, encoding="ascii")
    return value


def _sync_user_key(user: dict[str, Any]) -> str:
    return cloud_profile_id(user)

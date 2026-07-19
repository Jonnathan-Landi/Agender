from __future__ import annotations

import base64
import hashlib
import shutil
import threading
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

from .cloud_account import _access_token, _bytes_request, _json_request
from .config import APP_DATA_DIR, read_json, write_json_atomic

REMOTE_DATA_EXTENSIONS = {".csv", ".dat", ".txt", ".xlsx", ".parquet"}
REMOTE_CACHE_ROOT = APP_DATA_DIR / "remote-data"
_cache_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def materialize_source(user: dict[str, Any], settings: dict[str, Any], source: str) -> tuple[str, dict[str, Any]]:
    mode = settings[f"{source}DataSource"]
    if mode == "local":
        return settings[f"{source}DataPath"], {"mode": "local"}

    shared_url = settings[f"{source}OneDriveUrl"]
    if not shared_url:
        raise ValueError("Configura el enlace compartido de OneDrive o SharePoint.")

    user_key = hashlib.sha256(f"{user['id']}:{user['username']}".casefold().encode()).hexdigest()[:24]
    with _cache_locks[f"{user_key}:{source}"]:
        return _materialize_remote(user, source, shared_url, user_key)


def _materialize_remote(
    user: dict[str, Any],
    source: str,
    shared_url: str,
    user_key: str,
) -> tuple[str, dict[str, Any]]:
    token = _access_token(user, "onedrive")
    cache_root = REMOTE_CACHE_ROOT / user_key / source
    manifest_path = cache_root / ".agender-remote.json"
    previous = read_json(manifest_path, {})
    if previous and previous.get("url") != shared_url and cache_root.is_dir():
        shutil.rmtree(cache_root)
        previous = {}
    share_token = encode_share_url(shared_url)
    root = _json_request(
        f"https://graph.microsoft.com/v1.0/shares/{share_token}/driveItem"
        "?$select=id,name,parentReference,folder",
        headers={
            "Authorization": f"Bearer {token}",
            "Prefer": "redeemSharingLinkIfNecessary",
        },
    )
    if "folder" not in root:
        raise ValueError("El enlace debe apuntar a una carpeta compartida.")
    drive_id = (root.get("parentReference") or {}).get("driveId")
    if not drive_id or not root.get("id"):
        raise ValueError("OneDrive no devolvió una carpeta válida.")

    remote_files = _walk_folder(token, str(drive_id), str(root["id"]))
    previous_files = previous.get("files", {}) if previous.get("url") == shared_url else {}
    downloaded = reused = deleted = 0
    current: dict[str, Any] = {}
    cache_root.mkdir(parents=True, exist_ok=True)

    for item in remote_files:
        relative = item["relative"]
        target = _safe_target(cache_root, relative)
        fingerprint = {"id": item["id"], "eTag": item.get("eTag"), "size": item.get("size", 0)}
        old = previous_files.get(relative)
        if old == fingerprint and target.is_file():
            reused += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            content = _bytes_request(
                f"https://graph.microsoft.com/v1.0/drives/{urllib.parse.quote(str(drive_id), safe='')}"
                f"/items/{urllib.parse.quote(str(item['id']), safe='')}/content",
                headers={"Authorization": f"Bearer {token}"},
            )
            temporary = target.with_suffix(f"{target.suffix}.download")
            temporary.write_bytes(content)
            temporary.replace(target)
            downloaded += 1
        current[relative] = fingerprint

    for relative in set(previous_files) - set(current):
        target = _safe_target(cache_root, relative)
        if target.is_file():
            target.unlink()
            deleted += 1
    _remove_empty_directories(cache_root)
    write_json_atomic(manifest_path, {"version": 1, "url": shared_url, "files": current})
    return str(cache_root), {
        "mode": "onedrive",
        "remoteDownloaded": downloaded,
        "remoteReused": reused,
        "remoteDeleted": deleted,
    }


def encode_share_url(url: str) -> str:
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"u!{encoded}"


def _walk_folder(token: str, drive_id: str, root_id: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    folders = [(root_id, "")]
    files: list[dict[str, Any]] = []
    while folders:
        folder_id, prefix = folders.pop()
        url = (
            f"https://graph.microsoft.com/v1.0/drives/{urllib.parse.quote(drive_id, safe='')}"
            f"/items/{urllib.parse.quote(folder_id, safe='')}/children"
            "?$select=id,name,size,eTag,file,folder&$top=200"
        )
        while url:
            page = _json_request(url, headers=headers)
            for item in page.get("value", []):
                name = _safe_name(str(item.get("name") or ""))
                if not name:
                    continue
                relative = f"{prefix}/{name}".lstrip("/")
                if "folder" in item:
                    folders.append((str(item["id"]), relative))
                elif "file" in item and Path(name).suffix.casefold() in REMOTE_DATA_EXTENSIONS:
                    files.append({**item, "relative": relative})
            url = str(page.get("@odata.nextLink") or "")
    return files


def _safe_name(name: str) -> str:
    if name in {"", ".", ".."} or any(char in name for char in ("/", "\\", "\0")):
        return ""
    return name


def _safe_target(root: Path, relative: str) -> Path:
    target = (root / Path(relative)).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError("OneDrive devolvió una ruta de archivo no válida.")
    return target


def _remove_empty_directories(root: Path) -> None:
    for directory in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass

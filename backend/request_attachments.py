from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import Any

from .cloud_account import CloudHttpError, _access_token, _bytes_request, _json_request
from .cloud_identity import cloud_profile_id
from .config import APP_DATA_DIR
from .user_data import read_user_data

REQUESTS_KEY = "agender.request.records"
MAX_PDF_BYTES = 25 * 1024 * 1024
ATTACHMENT_ROLES = {"request", "response", "additional"}


def save_request_pdf_local(
    user: dict[str, Any], record_id: str, role: str, filename: str, content: bytes
) -> dict[str, Any]:
    record = _request_record(user, record_id)
    if role not in ATTACHMENT_ROLES:
        raise ValueError("Tipo de adjunto no válido")
    if not content or len(content) > MAX_PDF_BYTES:
        raise ValueError("El PDF debe pesar como máximo 25 MB")
    if not content.startswith(b"%PDF-"):
        raise ValueError("El archivo seleccionado no es un PDF válido")

    folder_name = _request_folder(record, record_id)
    attachment_id = uuid.uuid4().hex
    display_name = _safe_pdf_name(filename)
    remote_name = f"{attachment_id}-{display_name}"
    attachment = {
        "id": attachment_id,
        "role": role,
        "name": display_name,
        "remoteName": remote_name,
        "folder": folder_name,
        "size": len(content),
        "uploadedAt": datetime.now(UTC).isoformat(),
    }
    folder = _local_folder(user, folder_name)
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / remote_name
    temporary = output.with_suffix(".pdf.tmp")
    temporary.write_bytes(content)
    temporary.replace(output)
    _pending_path(output).write_text(json.dumps(attachment, ensure_ascii=False), encoding="utf-8")
    return attachment


def sync_request_pdf_to_onedrive(user: dict[str, Any], attachment: dict[str, Any]) -> dict[str, Any]:
    folder_name, remote_name = _attachment_location(attachment)
    local_file = _local_folder(user, folder_name) / remote_name
    if not local_file.is_file():
        raise FileNotFoundError("No se encontró el PDF local pendiente")
    content = local_file.read_bytes()
    token = _access_token(user, "onedrive")
    profile_folder = cloud_profile_id(user)
    _ensure_folder(token, "", "Solicitudes")
    _ensure_folder(token, "Solicitudes", profile_folder)
    _ensure_folder(token, f"Solicitudes/{profile_folder}", folder_name)
    remote_path = f"Solicitudes/{profile_folder}/{folder_name}/{remote_name}"
    url = f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/{_quote_path(remote_path)}:/content"
    result = _json_request(
        url,
        method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/pdf"},
        body=content,
    )
    _pending_path(local_file).unlink(missing_ok=True)
    return result


def flush_pending_attachments(user: dict[str, Any]) -> dict[str, int]:
    root = _local_root(user)
    synced = failed = 0
    if not root.is_dir():
        return {"attachmentsSynced": 0, "attachmentsFailed": 0}
    for pending in root.rglob("*.pending.json"):
        try:
            attachment = json.loads(pending.read_text(encoding="utf-8"))
            sync_request_pdf_to_onedrive(user, attachment)
            synced += 1
        except (ValueError, OSError, CloudHttpError, json.JSONDecodeError):
            failed += 1
    return {"attachmentsSynced": synced, "attachmentsFailed": failed}


def download_request_pdf(user: dict[str, Any], record_id: str, attachment_id: str) -> tuple[bytes, str]:
    record = _request_record(user, record_id)
    attachment = next(
        (
            item
            for item in record.get("attachments", [])
            if isinstance(item, dict) and str(item.get("id")) == attachment_id
        ),
        None,
    )
    if not attachment:
        raise FileNotFoundError("No se encontró el PDF solicitado")
    folder, remote_name = _attachment_location(attachment, record)
    local_file = _local_folder(user, folder) / remote_name
    if local_file.is_file():
        content = local_file.read_bytes()
        if content.startswith(b"%PDF-") and len(content) <= MAX_PDF_BYTES:
            return content, str(attachment.get("name") or "documento.pdf")
    profile_folder = cloud_profile_id(user)
    remote_path = f"Solicitudes/{profile_folder}/{folder}/{remote_name}"
    token = _access_token(user, "onedrive")
    url = f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/{_quote_path(remote_path)}:/content"
    content = _bytes_request(url, headers={"Authorization": f"Bearer {token}"})
    if not content.startswith(b"%PDF-") or len(content) > MAX_PDF_BYTES:
        raise ValueError("OneDrive devolvió un PDF no válido")
    local_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = local_file.with_suffix(".pdf.tmp")
    temporary.write_bytes(content)
    temporary.replace(local_file)
    return content, str(attachment.get("name") or "documento.pdf")


def resolve_request_pdf(user: dict[str, Any], record_id: str, attachment_id: str):
    record = _request_record(user, record_id)
    attachment = next(
        (
            item
            for item in record.get("attachments", [])
            if isinstance(item, dict) and str(item.get("id")) == attachment_id
        ),
        None,
    )
    if not attachment:
        raise FileNotFoundError("No se encontró el PDF solicitado")
    folder, remote_name = _attachment_location(attachment, record)
    local_file = _local_folder(user, folder) / remote_name
    if not local_file.is_file():
        download_request_pdf(user, record_id, attachment_id)
    return local_file, str(attachment.get("name") or "documento.pdf")


def delete_request_documents_local(user: dict[str, Any], record_id: str) -> dict[str, Any]:
    record = _request_record(user, record_id)
    folder_name = _request_folder(record, record_id)
    records = read_user_data(user).get(REQUESTS_KEY, [])
    shared = any(
        isinstance(item, dict)
        and str(item.get("id")) != record_id
        and _request_folder(item, str(item.get("id") or "request")) == folder_name
        for item in records
    )
    folder = _local_folder(user, folder_name)
    remote_names = []
    for attachment in record.get("attachments", []):
        if not isinstance(attachment, dict):
            continue
        try:
            attachment_folder, remote_name = _attachment_location(attachment, record)
        except ValueError:
            continue
        remote_names.append((attachment_folder, remote_name))
        local_file = _local_folder(user, attachment_folder) / remote_name
        local_file.unlink(missing_ok=True)
        _pending_path(local_file).unlink(missing_ok=True)
        if attachment_folder != folder_name:
            canonical_file = folder / remote_name
            canonical_file.unlink(missing_ok=True)
            _pending_path(canonical_file).unlink(missing_ok=True)
    if not shared and folder.is_dir():
        shutil.rmtree(folder)
    return {"folder": folder_name, "shared": shared, "remoteFiles": remote_names}


def delete_request_documents_onedrive(user: dict[str, Any], deletion: dict[str, Any]) -> None:
    token = _access_token(user, "onedrive")
    profile_folder = cloud_profile_id(user)
    targets = deletion.get("remoteFiles", []) if deletion.get("shared") else [(deletion.get("folder"), "")]
    for folder, remote_name in targets:
        remote_path = f"Solicitudes/{profile_folder}/{folder}"
        if remote_name:
            remote_path += f"/{remote_name}"
        url = f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/{_quote_path(remote_path)}"
        try:
            _json_request(url, method="DELETE", headers={"Authorization": f"Bearer {token}"})
        except CloudHttpError as error:
            if error.code != 404:
                raise


def open_request_folder(user: dict[str, Any], record_id: str) -> str:
    record = _request_record(user, record_id)
    folder_name = _request_folder(record, record_id)
    folder = _local_folder(user, folder_name)
    folder.mkdir(parents=True, exist_ok=True)
    for attachment in record.get("attachments", []):
        if not isinstance(attachment, dict) or not attachment.get("id"):
            continue
        try:
            content, _ = download_request_pdf(user, record_id, str(attachment["id"]))
            _, remote_name = _attachment_location(attachment, record)
            canonical_file = folder / remote_name
            if not canonical_file.is_file():
                temporary = canonical_file.with_suffix(".pdf.tmp")
                temporary.write_bytes(content)
                temporary.replace(canonical_file)
        except (ValueError, FileNotFoundError, CloudHttpError):
            continue
    if os.name == "nt":
        os.startfile(folder)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(folder)


def _attachment_location(
    attachment: dict[str, Any], record: dict[str, Any] | None = None
) -> tuple[str, str]:
    folder = str(attachment.get("folder") or (record or {}).get("attachmentFolder") or "")
    remote_name = str(attachment.get("remoteName") or "")
    if not _valid_segment(folder) or not re.fullmatch(r"[a-f0-9]{32}-.+\.pdf", remote_name, re.IGNORECASE):
        raise ValueError("La referencia del PDF no es válida")
    return folder, remote_name


def _local_root(user: dict[str, Any]):
    return APP_DATA_DIR / "request-documents" / cloud_profile_id(user)


def _local_folder(user: dict[str, Any], folder_name: str):
    if not _valid_segment(folder_name):
        raise ValueError("Nombre de carpeta no válido")
    return _local_root(user) / folder_name


def _pending_path(pdf_path):
    return pdf_path.with_name(f"{pdf_path.name}.pending.json")


def _request_record(user: dict[str, Any], record_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", record_id):
        raise ValueError("Identificador de solicitud no válido")
    records = read_user_data(user).get(REQUESTS_KEY, [])
    record = next(
        (item for item in records if isinstance(item, dict) and str(item.get("id")) == record_id),
        None,
    )
    if not record:
        raise FileNotFoundError("No se encontró la solicitud")
    return record


def _ensure_folder(token: str, parent: str, name: str) -> None:
    if not _valid_segment(name):
        raise ValueError("Nombre de carpeta no válido")
    if parent:
        url = f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/{_quote_path(parent)}:/children"
    else:
        url = "https://graph.microsoft.com/v1.0/me/drive/special/approot/children"
    payload = json.dumps(
        {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        _json_request(
            url,
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            body=payload,
        )
    except CloudHttpError as error:
        if error.code != 409:
            raise


def _request_folder(record: dict[str, Any], record_id: str) -> str:
    del record_id
    requester = _safe_folder_name(str(record.get("requester") or "SIN SOLICITANTE"), 96)
    return f"SOL_{requester}"


def _safe_folder_name(value: str, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", " ", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or "SIN SOLICITANTE")[:maximum].rstrip(" .")


def _safe_pdf_name(value: str) -> str:
    stem = value.rsplit(".", 1)[0] if "." in value else value
    return f"{_safe_segment(stem or 'documento', 90)}.pdf"


def _safe_segment(value: str, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", normalized)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    return (cleaned or "Sin_nombre")[:maximum].rstrip(" .")


def _valid_segment(value: str) -> bool:
    return bool(
        value
        and value not in {".", ".."}
        and len(value) <= 120
        and value == value.strip(" .")
        and not re.search(r"[<>:\"/\\|?*\x00-\x1f]", value)
    )


def _quote_path(value: str) -> str:
    return "/".join(urllib.parse.quote(segment, safe="") for segment in value.split("/"))

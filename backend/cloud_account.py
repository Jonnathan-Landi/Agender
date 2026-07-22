"""Microsoft account authorization and small Graph API helpers."""

from __future__ import annotations

import base64
import copy
import ctypes
import hashlib
import json
import os
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import APP_DATA_DIR, read_json, write_json_atomic

CLOUD_STATE_FILE = APP_DATA_DIR / "cloud.json"
TOKEN_SKEW_SECONDS = 90
DEFAULT_CLIENT_IDS = {
    "onedrive": "41680243-1eed-44c7-8ac5-20ba966f8209",
}

PROVIDERS = {
    "onedrive": {
        "label": "OneDrive",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": "offline_access User.Read Files.Read Files.ReadWrite.AppFolder",
    },
}


def cloud_status(user: dict[str, Any], base_url: str) -> dict[str, Any]:
    state = _read_state()
    providers: dict[str, Any] = {}
    for provider, config in PROVIDERS.items():
        entry = _provider_entry(state, user, provider)
        token = entry.get("token") if isinstance(entry, dict) else None
        connected = bool(isinstance(token, dict) and token.get("refresh_token"))
        providers[provider] = {
            "label": config["label"],
            "configured": bool(_client_id(entry, provider)),
            "usesDefaultClient": True,
            "connected": connected,
            "account": entry.get("account") if isinstance(entry, dict) else None,
            "syncEnabled": connected and bool(entry.get("syncEnabled", True)),
            "lastSyncAt": entry.get("lastSyncAt") if isinstance(entry, dict) else None,
            "lastSyncError": entry.get("lastSyncError") if isinstance(entry, dict) else None,
            "redirectUri": _redirect_uri(base_url, provider),
        }
    return {"providers": providers}


def set_sync_enabled(user: dict[str, Any], enabled: bool) -> dict[str, bool]:
    state = _read_state()
    entry = _provider_entry(state, user, "onedrive", create=True)
    entry["syncEnabled"] = bool(enabled)
    _write_state(state)
    return {"ok": True, "enabled": bool(enabled)}


def set_sync_result(user: dict[str, Any], result: dict[str, Any]) -> None:
    state = _read_state()
    entry = _provider_entry(state, user, "onedrive", create=True)
    if result.get("ok"):
        entry["lastSyncAt"] = result.get("syncedAt") or datetime.now(UTC).isoformat()
        entry.pop("lastSyncError", None)
    else:
        entry["lastSyncError"] = str(result.get("error") or "Error de sincronización")
    _write_state(state)


def start_auth(user: dict[str, Any], provider: str, base_url: str) -> dict[str, str]:
    _require_provider(provider)
    state = _read_state()
    entry = _provider_entry(state, user, provider, create=True)
    client_id = _client_id(entry, provider)
    if not client_id:
        raise ValueError("Primero pega el Client ID de este proveedor.")

    verifier = _code_verifier()
    challenge = _code_challenge(verifier)
    csrf = secrets.token_urlsafe(24)
    entry["pending"] = {
        "state": csrf,
        "verifier": verifier,
        "createdAt": time.time(),
        "redirectUri": _redirect_uri(base_url, provider),
    }
    _write_state(state)

    params = {
        "client_id": client_id,
        "redirect_uri": entry["pending"]["redirectUri"],
        "response_type": "code",
        "scope": PROVIDERS[provider]["scopes"],
        "state": csrf,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {"authUrl": f"{PROVIDERS[provider]['auth_url']}?{urllib.parse.urlencode(params)}"}


def finish_auth(provider: str, query: dict[str, str], base_url: str) -> str:
    _require_provider(provider)
    if query.get("error"):
        raise ValueError(query.get("error_description") or query["error"])
    code, csrf = query.get("code"), query.get("state")
    if not code or not csrf:
        raise ValueError("Respuesta OAuth incompleta.")

    state = _read_state()
    user_hash, entry = _find_pending_entry(state, provider, csrf)
    pending = entry.get("pending") or {}
    if time.time() - float(pending.get("createdAt", 0)) > 900:
        raise ValueError("El inicio de sesión expiró. Intenta de nuevo.")

    token = _post_form(
        PROVIDERS[provider]["token_url"],
        {
            "client_id": _client_id(entry, provider),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending.get("redirectUri") or _redirect_uri(base_url, provider),
            "code_verifier": pending["verifier"],
        },
    )
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    entry["token"] = token
    entry["account"] = _account_info(provider, token["access_token"])
    entry["syncEnabled"] = True
    entry.pop("pending", None)
    state["users"][user_hash][provider] = entry
    _write_state(state)
    return entry["account"].get("displayName") or entry["account"].get("email") or PROVIDERS[provider]["label"]


def disconnect(user: dict[str, Any], provider: str) -> dict[str, bool]:
    _require_provider(provider)
    state = _read_state()
    entry = _provider_entry(state, user, provider, create=True)
    entry.pop("token", None)
    entry.pop("account", None)
    _write_state(state)
    return {"ok": True}


def _access_token(user: dict[str, Any], provider: str) -> str:
    _require_provider(provider)
    state = _read_state()
    entry = _provider_entry(state, user, provider)
    token = entry.get("token") if isinstance(entry, dict) else None
    if not isinstance(token, dict) or not token.get("refresh_token"):
        raise ValueError("Primero inicia sesión en la nube.")
    if float(token.get("expires_at", 0)) > time.time() + TOKEN_SKEW_SECONDS and token.get("access_token"):
        return token["access_token"]
    refreshed = _post_form(
        PROVIDERS[provider]["token_url"],
        {
            "client_id": _client_id(entry, provider),
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        },
    )
    refreshed["refresh_token"] = refreshed.get("refresh_token") or token["refresh_token"]
    refreshed["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
    entry["token"] = refreshed
    _write_state(state)
    return refreshed["access_token"]


def _client_id(entry: Any, provider: str) -> str:
    return str(DEFAULT_CLIENT_IDS.get(provider, "")).strip()


def _account_info(provider: str, access_token: str) -> dict[str, str]:
    data = _json_request("https://graph.microsoft.com/v1.0/me", headers={"Authorization": f"Bearer {access_token}"})
    return {
        "email": data.get("mail") or data.get("userPrincipalName", ""),
        "displayName": data.get("displayName") or data.get("userPrincipalName", ""),
    }


def _post_form(url: str, values: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(values).encode("utf-8")
    return _json_request(url, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=body)


def _json_request(
    url: str, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None
) -> dict[str, Any]:
    data = _bytes_request(url, method, headers, body)
    try:
        return json.loads(data.decode("utf-8")) if data else {}
    except json.JSONDecodeError as error:
        raise ValueError("La nube respondió con un formato no válido.") from error


def _bytes_request(
    url: str, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None
) -> bytes:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        opener = urllib.request.build_opener(_SafeRedirectHandler())
        with opener.open(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise CloudHttpError(error.code, detail) from error
    except urllib.error.URLError as error:
        raise ValueError(f"No fue posible conectar con la nube: {error.reason}") from error


def download_to_file(url: str, target: Path, headers: dict[str, str] | None = None) -> None:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        opener = urllib.request.build_opener(_SafeRedirectHandler())
        with opener.open(request, timeout=120) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise CloudHttpError(error.code, detail) from error
    except urllib.error.URLError as error:
        raise ValueError(f"No fue posible conectar con la nube: {error.reason}") from error


class CloudHttpError(ValueError):
    def __init__(self, code: int, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"Error de nube {code}: {detail}")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> urllib.request.Request | None:
        redirected = super().redirect_request(request, file_pointer, code, message, headers, new_url)
        if redirected is None:
            return None

        source_host = urllib.parse.urlsplit(request.full_url).netloc.casefold()
        target_host = urllib.parse.urlsplit(new_url).netloc.casefold()
        if source_host != target_host:
            redirected.remove_header("Authorization")
        return redirected


def _redirect_uri(base_url: str, provider: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    port = f":{parsed.port}" if parsed.port else ""
    return f"http://localhost{port}/api/cloud/auth/callback/{provider}"


def _find_pending_entry(state: dict[str, Any], provider: str, csrf: str) -> tuple[str, dict[str, Any]]:
    for user_hash, providers in state.get("users", {}).items():
        entry = providers.get(provider) if isinstance(providers, dict) else None
        if isinstance(entry, dict) and (entry.get("pending") or {}).get("state") == csrf:
            return user_hash, entry
    raise ValueError("No se encontró una sesión OAuth pendiente.")


def _provider_entry(state: dict[str, Any], user: dict[str, Any], provider: str, create: bool = False) -> dict[str, Any]:
    user_hash = _user_hash(user)
    if create:
        state.setdefault("users", {}).setdefault(user_hash, {}).setdefault(provider, {})
    return state.get("users", {}).get(user_hash, {}).get(provider, {})


def _read_state() -> dict[str, Any]:
    data = read_json(CLOUD_STATE_FILE, {"users": {}})
    if not isinstance(data, dict):
        return {"users": {}}
    for providers in data.get("users", {}).values():
        if not isinstance(providers, dict):
            continue
        for entry in providers.values():
            if not isinstance(entry, dict) or "protectedToken" not in entry:
                continue
            try:
                token_json = _unprotect_data(base64.b64decode(entry.pop("protectedToken"))).decode("utf-8")
                entry["token"] = json.loads(token_json)
            except (ValueError, OSError, json.JSONDecodeError):
                entry.pop("token", None)
    return data


def _write_state(state: dict[str, Any]) -> None:
    protected = copy.deepcopy(state)
    for providers in protected.get("users", {}).values():
        if not isinstance(providers, dict):
            continue
        for entry in providers.values():
            if not isinstance(entry, dict) or not isinstance(entry.get("token"), dict):
                continue
            token = json.dumps(entry.pop("token"), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            entry["protectedToken"] = base64.b64encode(_protect_data(token)).decode("ascii")
    write_json_atomic(CLOUD_STATE_FILE, protected)


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _protect_data(content: bytes) -> bytes:
    if os.name != "nt":
        return content
    return _crypt_protect(content, decrypt=False)


def _unprotect_data(content: bytes) -> bytes:
    if os.name != "nt":
        return content
    return _crypt_protect(content, decrypt=True)


def _crypt_protect(content: bytes, decrypt: bool) -> bytes:
    buffer = ctypes.create_string_buffer(content)
    source = _DataBlob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise OSError(ctypes.get_last_error(), "Windows no pudo proteger las credenciales")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


def _user_hash(user: dict[str, Any]) -> str:
    identity = f"{user.get('id')}:{user.get('username', '')}".casefold()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _require_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError("Proveedor de nube no válido.")


def _code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii").rstrip("=")


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

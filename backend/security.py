from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import APP_DATA_DIR

ALL_MODULES = {"hydromet", "viewer", "requests", "diary", "agenda", "settings", "licenses"}
DB_PATH = APP_DATA_DIR / "users.db"
PUBLIC_KEY_PATH = Path(__file__).resolve().parent / "security" / "license_public_key.pem"
PROGRAM_DATA_ROOT = Path(os.environ.get("PROGRAMDATA", APP_DATA_DIR.parent))
PROGRAM_DATA = PROGRAM_DATA_ROOT / "Agender"
LICENSE_PATHS = (APP_DATA_DIR / "license.json", PROGRAM_DATA / "license.json", Path.cwd() / "license.json")
PRIVATE_KEY_PATHS = (APP_DATA_DIR / "authority" / "license_private_key.pem", Path.cwd() / "license-authority" / "license_private_key.pem")
password_hasher = PasswordHasher()
_sessions: dict[str, tuple[int, datetime]] = {}
_lock = Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')),
        enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "must_change_password" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
    if "license_id" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN license_id TEXT")
    connection.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    return connection


@contextmanager
def database():
    connection = _connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def canonical_license(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def validate_license_payload(payload: dict[str, Any]) -> dict[str, Any]:
    signature = base64.b64decode(payload["signature"], validate=True)
    public_key = serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("Clave pública no válida")
    public_key.verify(signature, canonical_license(payload))
    expiry = payload.get("expiresAt")
    if expiry and datetime.fromisoformat(expiry).date() < datetime.now(UTC).date():
        raise ValueError("La licencia ha expirado")
    payload = dict(payload)
    payload["modules"] = sorted(set(payload.get("modules", [])) & ALL_MODULES)
    payload["valid"] = True
    return payload


def read_license() -> dict[str, Any]:
    path = next((candidate for candidate in LICENSE_PATHS if candidate.is_file()), None)
    if not path:
        return {"valid": False, "reason": "No hay una licencia instalada", "modules": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {**validate_license_payload(payload), "path": str(path)}
    except Exception as error:
        return {"valid": False, "reason": f"Licencia no válida: {error}", "modules": []}


def install_license(content: bytes, username: str, temporary_password: str) -> dict[str, Any]:
    payload = validate_license_payload(json.loads(content.decode("utf-8")))
    provision = payload.get("provision") or {}
    if provision.get("username", "").casefold() != username.strip().casefold():
        raise ValueError("La licencia no corresponde a este usuario")
    try:
        password_hasher.verify(provision["passwordHash"], temporary_password)
    except (KeyError, VerifyMismatchError, InvalidHashError) as error:
        raise ValueError("Usuario o clave temporal incorrectos") from error
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DATA_DIR / "license.json").write_bytes(content)
    _provision_user(payload, must_change=True)
    return payload


def _provision_user(license_data: dict[str, Any], must_change: bool = False) -> None:
    provision = license_data.get("provision") or {}
    username, password_hash = provision.get("username"), provision.get("passwordHash")
    if not username or not password_hash:
        return
    role = "admin" if provision.get("role") == "admin" else "user"
    with database() as connection:
        connection.execute("""INSERT INTO users(username,password_hash,role,created_at,must_change_password,license_id)
            VALUES(?,?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash,
            role=excluded.role,must_change_password=excluded.must_change_password,license_id=excluded.license_id""",
            (username, password_hash, role, datetime.now(UTC).isoformat(), int(must_change), license_data.get("licenseId")))


def login(username: str, password: str) -> tuple[str, dict[str, Any]] | None:
    license_data = read_license()
    if not license_data["valid"]:
        return None
    with database() as connection:
        row = connection.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username.strip(),)).fetchone()
    if not row:
        password_hasher.hash(password)  # reduce timing difference
        return None
    try:
        password_hasher.verify(row["password_hash"], password)
    except (VerifyMismatchError, InvalidHashError):
        return None
    token = secrets.token_urlsafe(32)
    with database() as connection:
        connection.execute("INSERT INTO sessions(token_hash,user_id,created_at) VALUES(?,?,?)",
                           (_token_hash(token), row["id"], datetime.now(UTC).isoformat()))
    return token, user_payload(row, license_data)


def current_user(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with database() as connection:
        row = connection.execute("SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND users.enabled=1",
                                 (_token_hash(token),)).fetchone()
    return user_payload(row, read_license()) if row else None


def logout(token: str | None) -> None:
    if token:
        with database() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def change_password(token: str | None, new_password: str) -> dict[str, Any]:
    user = current_user(token)
    if not user:
        raise ValueError("Sesión no válida")
    if len(new_password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    with database() as connection:
        connection.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
                           (password_hasher.hash(new_password), user["id"]))
    return current_user(token) or user


def user_payload(row: sqlite3.Row, license_data: dict[str, Any]) -> dict[str, Any]:
    admin = row["role"] == "admin"
    return {"id": row["id"], "username": row["username"], "role": row["role"], "mustChangePassword": bool(row["must_change_password"]),
            "modules": sorted(ALL_MODULES if admin else license_data.get("modules", []))}


def auth_status(token: str | None) -> dict[str, Any]:
    license_data = read_license()
    return {"license": {key: license_data.get(key) for key in ("valid", "reason", "licenseId", "customer", "expiresAt", "modules")},
            "user": current_user(token), "authorityAvailable": any(path.is_file() for path in PRIVATE_KEY_PATHS)}


def generate_license(values: dict[str, Any]) -> bytes:
    path = next((candidate for candidate in PRIVATE_KEY_PATHS if candidate.is_file()), None)
    if not path:
        raise ValueError("Este equipo no posee la clave privada de la autoridad")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Clave privada no válida")
    requested = set(values.get("modules", [])) & {"hydromet", "requests", "diary", "agenda"}
    modules = set(requested)
    if "hydromet" in requested:
        modules.update({"viewer", "settings"})
    modules = sorted(modules)
    if not modules:
        raise ValueError("Selecciona al menos un permiso")
    payload = {"version": 1, "licenseId": values["licenseId"], "customer": values["fullName"],
               "issuedAt": datetime.now(UTC).date().isoformat(), "expiresAt": values.get("expiresAt"), "modules": modules,
               "provision": {"fullName": values["fullName"], "username": values["username"],
                             "passwordHash": password_hasher.hash(values["temporaryPassword"]), "role": "user"}}
    payload["signature"] = base64.b64encode(key.sign(canonical_license(payload))).decode()
    return json.dumps(payload, ensure_ascii=False, indent=2).encode()


def install_authority_key(content: bytes) -> None:
    try:
        private_key = serialization.load_pem_private_key(content, password=None)
        public_key = serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
        if not isinstance(private_key, Ed25519PrivateKey) or not isinstance(public_key, Ed25519PublicKey):
            raise ValueError
        generated = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        expected = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if generated != expected:
            raise ValueError
    except Exception as error:
        raise ValueError("La clave privada no corresponde a la autoridad de Agender") from error
    target = APP_DATA_DIR / "authority" / "license_private_key.pem"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

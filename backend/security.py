from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import APP_DATA_DIR

REPORT_MODULES = {"report-water-quality", "report-hydromet-network"}
ALL_MODULES = {
    "hydromet",
    "viewer",
    "requests",
    "diary",
    "agenda",
    "reports",
    *REPORT_MODULES,
    "settings",
    "licenses",
}
DB_PATH = APP_DATA_DIR / "users.db"
PUBLIC_KEY_PATH = Path(__file__).resolve().parent / "security" / "license_public_key.pem"
PROGRAM_DATA_ROOT = Path(os.environ.get("PROGRAMDATA", APP_DATA_DIR.parent))
PROGRAM_DATA = PROGRAM_DATA_ROOT / "Agender"
LICENSE_PATHS = (APP_DATA_DIR / "license.json", PROGRAM_DATA / "license.json", Path.cwd() / "license.json")
PRIVATE_KEY_PATHS = (
    APP_DATA_DIR / "authority" / "license_private_key.pem",
)
password_hasher = PasswordHasher()
_sessions: dict[str, tuple[int, datetime]] = {}
_lock = Lock()
SESSION_ABSOLUTE_TTL = timedelta(hours=24)
SESSION_IDLE_TTL = timedelta(hours=1)
LOGIN_FAILURE_WINDOW = timedelta(minutes=5)
LOGIN_LOCKOUT = timedelta(minutes=15)
LOGIN_MAX_FAILURES = 5
_login_failures: dict[str, list[datetime]] = {}
_login_blocked_until: dict[str, datetime] = {}


class LoginRateLimited(ValueError):
    def __init__(self, retry_after: int):
        super().__init__("Demasiados intentos. Inténtalo de nuevo más tarde")
        self.retry_after = max(1, retry_after)


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
    if "license_revision" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN license_revision INTEGER NOT NULL DEFAULT 1")
    connection.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    session_columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
    if "last_seen_at" not in session_columns:
        connection.execute("ALTER TABLE sessions ADD COLUMN last_seen_at TEXT")
        connection.execute("UPDATE sessions SET last_seen_at=created_at WHERE last_seen_at IS NULL")
    connection.execute("""CREATE TABLE IF NOT EXISTS user_data (
        user_id INTEGER NOT NULL, data_key TEXT NOT NULL, value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY(user_id, data_key),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS sync_tombstones (
        user_id INTEGER NOT NULL, data_key TEXT NOT NULL, record_id TEXT NOT NULL,
        deleted_at TEXT NOT NULL, device_id TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(user_id, data_key, record_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS sync_record_meta (
        user_id INTEGER NOT NULL, data_key TEXT NOT NULL, record_id TEXT NOT NULL,
        updated_at TEXT NOT NULL, device_id TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(user_id, data_key, record_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS sync_conflicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        data_key TEXT NOT NULL, record_id TEXT NOT NULL,
        local_json TEXT NOT NULL, remote_json TEXT NOT NULL,
        detected_at TEXT NOT NULL, resolved_at TEXT,
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
    try:
        signature = base64.b64decode(payload["signature"], validate=True)
        public_key = serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("Clave pública no válida")
        public_key.verify(signature, canonical_license(payload))
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("Firma de licencia no válida") from error
    except Exception as error:
        raise ValueError("La firma de la licencia no coincide") from error
    expiry = payload.get("expiresAt")
    if expiry and datetime.fromisoformat(expiry).date() < datetime.now(UTC).date():
        raise ValueError("La licencia ha expirado")
    try:
        revision = int(payload.get("revision") or 1)
    except (TypeError, ValueError) as error:
        raise ValueError("La revisión de la licencia no es válida") from error
    if revision < 1:
        raise ValueError("La revisión de la licencia debe ser mayor o igual a 1")
    payload = dict(payload)
    payload["revision"] = revision
    payload["modules"] = sorted(_expand_module_access(payload.get("modules", [])))
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
    normalized_username = username.strip()
    if provision.get("username", "").casefold() != normalized_username.casefold():
        raise ValueError("La licencia no corresponde a este usuario")
    try:
        password_hasher.verify(provision["passwordHash"], temporary_password)
    except (KeyError, VerifyMismatchError, InvalidHashError) as error:
        raise ValueError("Usuario o clave temporal incorrectos") from error

    with database() as connection:
        existing = connection.execute(
            "SELECT license_id,license_revision FROM users WHERE username=?",
            (normalized_username,),
        ).fetchone()
    if existing:
        same_license = payload.get("licenseId") == existing["license_id"]
        current_revision = int(existing["license_revision"] or 1)
        if same_license and payload["revision"] <= current_revision:
            raise ValueError(f"La revisión debe ser superior a {current_revision}")

    _write_license_atomic(content)
    _provision_user(payload, must_change=True)
    return payload


def replace_license(content: bytes, token: str | None) -> dict[str, Any]:
    user = current_user(token)
    if not user:
        raise ValueError("Debes iniciar sesión")
    payload = validate_license_payload(json.loads(content.decode("utf-8")))
    provision = payload.get("provision") or {}
    if provision.get("username", "").casefold() != user["username"].casefold():
        raise ValueError("La licencia no corresponde al usuario actual")

    with database() as connection:
        row = connection.execute(
            "SELECT license_id,license_revision FROM users WHERE id=?",
            (user["id"],),
        ).fetchone()
    current_license_id = row["license_id"] if row else None
    current_revision = int(row["license_revision"] or 1) if row else 1
    new_revision = int(payload.get("revision") or 1)
    if payload.get("licenseId") == current_license_id and new_revision <= current_revision:
        raise ValueError(f"La revisión debe ser superior a {current_revision}")

    _write_license_atomic(content)
    with database() as connection:
        connection.execute(
            "UPDATE users SET license_id=?,license_revision=? WHERE id=?",
            (payload.get("licenseId"), new_revision, user["id"]),
        )
    return current_user(token) or user


def _write_license_atomic(content: bytes) -> None:
    target = APP_DATA_DIR / "license.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_bytes(content)
    temporary.replace(target)


def _provision_user(license_data: dict[str, Any], must_change: bool = False) -> None:
    provision = license_data.get("provision") or {}
    username, password_hash = provision.get("username"), provision.get("passwordHash")
    if not username or not password_hash:
        return
    role = "admin" if provision.get("role") == "admin" else "user"
    with database() as connection:
        connection.execute(
            """INSERT INTO users(
                username,password_hash,role,created_at,must_change_password,license_id,license_revision
            ) VALUES(?,?,?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET
            password_hash=excluded.password_hash,role=excluded.role,
            must_change_password=excluded.must_change_password,license_id=excluded.license_id,
            license_revision=excluded.license_revision""",
            (
                username,
                password_hash,
                role,
                datetime.now(UTC).isoformat(),
                int(must_change),
                license_data.get("licenseId"),
                int(license_data.get("revision") or 1),
            ),
        )


def _check_login_rate(normalized_username: str, now: datetime) -> None:
    with _lock:
        blocked_until = _login_blocked_until.get(normalized_username)
        if blocked_until and blocked_until > now:
            raise LoginRateLimited(int((blocked_until - now).total_seconds()) + 1)
        _login_blocked_until.pop(normalized_username, None)
        cutoff = now - LOGIN_FAILURE_WINDOW
        recent = [attempt for attempt in _login_failures.get(normalized_username, []) if attempt > cutoff]
        if recent:
            _login_failures[normalized_username] = recent
        else:
            _login_failures.pop(normalized_username, None)


def _record_login_failure(normalized_username: str, now: datetime) -> None:
    with _lock:
        cutoff = now - LOGIN_FAILURE_WINDOW
        attempts = [attempt for attempt in _login_failures.get(normalized_username, []) if attempt > cutoff]
        attempts.append(now)
        if len(attempts) >= LOGIN_MAX_FAILURES:
            _login_failures.pop(normalized_username, None)
            _login_blocked_until[normalized_username] = now + LOGIN_LOCKOUT
        else:
            _login_failures[normalized_username] = attempts


def _clear_login_failures(normalized_username: str) -> None:
    with _lock:
        _login_failures.pop(normalized_username, None)
        _login_blocked_until.pop(normalized_username, None)


def _create_session(connection: sqlite3.Connection, user_id: int, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    timestamp = now.isoformat()
    connection.execute(
        "INSERT INTO sessions(token_hash,user_id,created_at,last_seen_at) VALUES(?,?,?,?)",
        (_token_hash(token), user_id, timestamp, timestamp),
    )
    return token


def login(username: str, password: str) -> tuple[str, dict[str, Any]] | None:
    license_data = read_license()
    if not license_data["valid"]:
        return None
    normalized_username = username.strip().casefold()
    now = datetime.now(UTC)
    _check_login_rate(normalized_username, now)
    with database() as connection:
        row = connection.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username.strip(),)).fetchone()
    if not row:
        password_hasher.hash(password)  # reduce timing difference
        _record_login_failure(normalized_username, now)
        return None
    try:
        password_hasher.verify(row["password_hash"], password)
    except (VerifyMismatchError, InvalidHashError):
        _record_login_failure(normalized_username, now)
        return None
    _clear_login_failures(normalized_username)
    with database() as connection:
        token = _create_session(connection, row["id"], now)
    return token, user_payload(row, license_data)


def current_user(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    license_data = read_license()
    if not license_data.get("valid"):
        return None
    now = datetime.now(UTC)
    token_hash = _token_hash(token)
    with database() as connection:
        row = connection.execute(
            "SELECT users.*,sessions.created_at AS session_created_at,"
            "sessions.last_seen_at AS session_last_seen_at FROM sessions "
            "JOIN users ON users.id=sessions.user_id "
            "WHERE sessions.token_hash=? AND users.enabled=1",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        try:
            created_at = datetime.fromisoformat(row["session_created_at"])
            last_seen_at = datetime.fromisoformat(row["session_last_seen_at"] or row["session_created_at"])
        except (TypeError, ValueError):
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
            return None
        if now - created_at > SESSION_ABSOLUTE_TTL or now - last_seen_at > SESSION_IDLE_TTL:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
            return None
        connection.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now.isoformat(), token_hash))
    return user_payload(row, license_data) if row else None


def logout(token: str | None) -> None:
    if token:
        with database() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def change_password(token: str | None, new_password: str) -> tuple[str, dict[str, Any]]:
    user = current_user(token)
    if not user:
        raise ValueError("Sesión no válida")
    if len(new_password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    with database() as connection:
        connection.execute(
            "UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
            (password_hasher.hash(new_password), user["id"]),
        )
        connection.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        new_token = _create_session(connection, user["id"], datetime.now(UTC))
        row = connection.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    return new_token, user_payload(row, read_license())


def user_payload(row: sqlite3.Row, license_data: dict[str, Any]) -> dict[str, Any]:
    admin = row["role"] == "admin"
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "mustChangePassword": bool(row["must_change_password"]),
        "modules": sorted(ALL_MODULES if admin else _expand_module_access(license_data.get("modules", []))),
    }


def auth_status(token: str | None) -> dict[str, Any]:
    license_data = read_license()
    return {
        "license": {
            key: license_data.get(key)
            for key in ("valid", "reason", "licenseId", "revision", "customer", "expiresAt", "modules")
        },
        "user": current_user(token),
        "authorityAvailable": any(path.is_file() for path in PRIVATE_KEY_PATHS),
    }


def generate_license(values: dict[str, Any]) -> bytes:
    path = next((candidate for candidate in PRIVATE_KEY_PATHS if candidate.is_file()), None)
    if not path:
        raise ValueError("Este equipo no posee la clave privada de la autoridad")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Clave privada no válida")
    requested = set(values.get("modules", [])) & {
        "hydromet",
        "requests",
        "diary",
        "agenda",
        "reports",
        *REPORT_MODULES,
    }
    modules = _expand_module_access(requested)
    if "hydromet" in requested:
        modules.update({"viewer", "settings"})
    modules = sorted(modules)
    if not modules:
        raise ValueError("Selecciona al menos un permiso")
    revision = int(values.get("revision") or 1)
    if revision < 1:
        raise ValueError("La revisión debe ser mayor o igual a 1")
    payload = {
        "version": 2,
        "revision": revision,
        "licenseId": values["licenseId"],
        "customer": values["fullName"],
        "issuedAt": datetime.now(UTC).date().isoformat(),
        "expiresAt": values.get("expiresAt"),
        "modules": modules,
        "provision": {
            "fullName": values["fullName"],
            "username": values["username"],
            "passwordHash": password_hasher.hash(values["temporaryPassword"]),
            "role": "user",
        },
    }
    payload["signature"] = base64.b64encode(key.sign(canonical_license(payload))).decode()
    return json.dumps(payload, ensure_ascii=False, indent=2).encode()


def _expand_module_access(values: Any) -> set[str]:
    modules = set(values or []) & ALL_MODULES
    selected_reports = modules & REPORT_MODULES
    if "reports" in modules and not selected_reports:
        modules.update(REPORT_MODULES)  # compatibilidad con licencias anteriores
    elif selected_reports:
        modules.add("reports")
    if "hydromet" in modules:
        modules.update({"viewer", "settings"})
    return modules


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
    if os.name == "nt":
        identity = "\\".join(
            value for value in (os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")) if value
        )
        try:
            subprocess.run(
                [
                    "icacls",
                    str(target),
                    "/inheritance:r",
                    "/grant:r",
                    f"{identity}:(F)",
                    "*S-1-5-18:(F)",
                    "*S-1-5-32-544:(F)",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            target.unlink(missing_ok=True)
            raise ValueError("No fue posible proteger la clave privada en este equipo") from error

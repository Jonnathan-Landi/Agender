from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .cloud_account import (
    cloud_status,
    disconnect,
    finish_auth,
    set_sync_enabled,
    start_auth,
)
from .cloud_sync import synchronize_onedrive
from .config import read_settings, write_settings
from .portable_profile import PROFILE_SOURCES_KEY, portable_onedrive_sources
from .desktop_dialogs import choose_directory
from .lazy_asgi import LazyAsgiApp
from .onedrive_folders import materialize_source
from .security import (
    auth_status,
    change_password,
    current_user,
    generate_license,
    install_authority_key,
    install_license,
    replace_license,
    login,
    logout,
)
from .user_data import read_user_data, write_user_data

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
app = FastAPI(title="Agender", docs_url=None, redoc_url=None)
viewer_app = LazyAsgiApp("backend.viewer.api", "app")


@app.middleware("http")
async def enforce_module_access(request: Request, call_next):
    path = request.url.path
    required = None
    if path.startswith("/api/local-data"):
        required = "hydromet"
    elif path.startswith("/api/settings") or path.startswith("/api/select-directory"):
        required = "settings"
    elif path.startswith("/viewer-api"):
        required = "viewer"
    if required:
        user = current_user(request.cookies.get("agender_session"))
        if not user:
            return Response(content='{"detail":"Debes iniciar sesión"}', status_code=401, media_type="application/json")
        if required not in user["modules"]:
            return Response(content='{"detail":"Módulo no autorizado"}', status_code=403, media_type="application/json")
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        "connect-src 'self' ipc: http://ipc.localhost; "
        "frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class PathSettings(BaseModel):
    rawDataPath: str = ""
    qualityDataPath: str = ""
    rawDataSource: str = "local"
    qualityDataSource: str = "local"
    rawOneDriveUrl: str = ""
    qualityOneDriveUrl: str = ""
    rawIncludeSubfolders: bool = True
    qualityIncludeSubfolders: bool = True


class DirectoryRequest(BaseModel):
    initialPath: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    password: str


class UserDataValue(BaseModel):
    value: object


class CloudSyncToggle(BaseModel):
    enabled: bool


class ExcelTableExport(BaseModel):
    filename: str
    headers: list[str]
    rows: list[list[Any]]


class LicenseGenerationRequest(BaseModel):
    licenseId: str
    fullName: str
    username: str
    temporaryPassword: str
    expiresAt: str | None = None
    revision: int = 1
    modules: list[str]


@app.get("/api/auth/status")
def get_auth_status(request: Request) -> dict[str, object]:
    return auth_status(request.cookies.get("agender_session"))


@app.post("/api/auth/login")
def post_login(credentials: LoginRequest, response: Response) -> dict[str, object]:
    result = login(credentials.username, credentials.password)
    if not result:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token, user = result
    response.set_cookie("agender_session", token, httponly=True, samesite="strict", secure=False, max_age=315360000)
    return {"user": user}


@app.post("/api/auth/activate")
async def activate_license(
    response: Response, username: str = Form(...), password: str = Form(...), license: UploadFile = File(...)
) -> dict[str, object]:
    try:
        install_license(await license.read(), username, password)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    result = login(username, password)
    if not result:
        raise HTTPException(status_code=401, detail="No fue posible activar el usuario")
    token, user = result
    response.set_cookie("agender_session", token, httponly=True, samesite="strict", secure=False, max_age=315360000)
    return {"user": user}


@app.post("/api/auth/change-password")
def post_change_password(request: Request, values: PasswordChangeRequest) -> dict[str, object]:
    try:
        return {"user": change_password(request.cookies.get("agender_session"), values.password)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/auth/license")
async def put_current_license(request: Request, license: UploadFile = File(...)) -> dict[str, object]:
    try:
        user = replace_license(await license.read(), request.cookies.get("agender_session"))
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"user": user}


@app.post("/api/licenses/generate")
def post_generate_license(request: Request, values: LicenseGenerationRequest) -> Response:
    user = current_user(request.cookies.get("agender_session"))
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede generar licencias")
    try:
        content = generate_license(values.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    filename = f"{values.licenseId}.license.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/licenses/import-authority")
async def import_authority_key(request: Request, key: UploadFile = File(...)) -> dict[str, bool]:
    user = current_user(request.cookies.get("agender_session"))
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede importar la autoridad")
    try:
        install_authority_key(await key.read())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"ok": True}


@app.post("/api/auth/logout")
def post_logout(request: Request, response: Response) -> dict[str, bool]:
    logout(request.cookies.get("agender_session"))
    response.delete_cookie("agender_session")
    return {"ok": True}


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "source": "local", "backend": "python"}


@app.get("/api/app-info")
def app_info() -> dict[str, str]:
    config = json.loads((PROJECT_ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    return {"name": config.get("productName", "Agender"), "version": config.get("version", "")}


@app.get("/api/user-data")
def get_user_data(request: Request) -> dict[str, object]:
    user = current_user(request.cookies.get("agender_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")
    return {"data": read_user_data(user)}


def _require_user(request: Request) -> dict[str, Any]:
    user = current_user(request.cookies.get("agender_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")
    return user


@app.get("/api/cloud/status")
def get_cloud_status(request: Request) -> dict[str, object]:
    return cloud_status(_require_user(request), str(request.base_url))


@app.post("/api/cloud/{provider}/auth/start")
def post_cloud_auth_start(provider: str, request: Request) -> dict[str, str]:
    try:
        result = start_auth(_require_user(request), provider, str(request.base_url))
        if not webbrowser.open(result["authUrl"], new=2):
            raise ValueError("No fue posible abrir el navegador predeterminado.")
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/cloud/auth/callback/{provider}")
def cloud_auth_callback(provider: str, request: Request) -> Response:
    try:
        account = finish_auth(provider, dict(request.query_params), str(request.base_url))
    except ValueError as error:
        content = f"<html><body><h1>No fue posible conectar</h1><p>{error}</p></body></html>"
        return Response(content=content, media_type="text/html", status_code=400)
    content = f"<html><body><h1>Cuenta conectada</h1><p>{account}</p><p>Ya puedes volver a Agender.</p></body></html>"
    return Response(content=content, media_type="text/html")


@app.post("/api/cloud/{provider}/disconnect")
def post_cloud_disconnect(provider: str, request: Request) -> dict[str, bool]:
    try:
        return disconnect(_require_user(request), provider)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/cloud/onedrive/sync")
def put_onedrive_sync(payload: CloudSyncToggle, request: Request) -> dict[str, bool]:
    try:
        return set_sync_enabled(_require_user(request), payload.enabled)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/cloud/onedrive/sync")
def post_onedrive_sync(request: Request) -> dict[str, object]:
    try:
        return synchronize_onedrive(_require_user(request))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/user-data/{key}")
def put_user_data(key: str, payload: UserDataValue, request: Request) -> dict[str, bool]:
    user = current_user(request.cookies.get("agender_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")
    try:
        write_user_data(user, key, payload.value)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"ok": True}


@app.get("/api/settings/paths")
def get_paths(request: Request) -> dict[str, object]:
    user = current_user(request.cookies.get("agender_session"))
    return read_settings(user["username"], user["role"] == "admin")


@app.put("/api/settings/paths")
def put_paths(settings: PathSettings, request: Request) -> dict[str, object]:
    user = current_user(request.cookies.get("agender_session"))
    try:
        saved = write_settings(settings.model_dump(), user["username"], user["role"] == "admin")
        existing = read_user_data(user).get(PROFILE_SOURCES_KEY, {})
        portable = portable_onedrive_sources(saved, existing)
        if portable != existing:
            write_user_data(user, PROFILE_SOURCES_KEY, portable)
        return saved
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/select-directory")
async def select_directory(request: DirectoryRequest) -> dict[str, str]:
    selected = await run_in_threadpool(_folder_dialog, request.initialPath)
    return {"path": selected}


@app.get("/api/local-data")
async def local_data(
    request: Request,
    source: str = Query(default="raw", pattern="^(raw|quality)$"),
    refresh: bool = Query(default=True),
) -> dict[str, object]:
    if not refresh:
        return await run_in_threadpool(_inventory_snapshot, source)
    user = current_user(request.cookies.get("agender_session"))
    settings = read_settings(user["username"], user["role"] == "admin")
    recursive = settings["rawIncludeSubfolders" if source == "raw" else "qualityIncludeSubfolders"]
    try:
        root, remote_sync = await run_in_threadpool(materialize_source, user, settings, source)
        result = await run_in_threadpool(_synchronize_inventory, source, root, recursive)
        result["storage"] = remote_sync
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _synchronize_inventory(source: str, root: str, recursive: bool) -> dict[str, Any]:
    from .indexer import synchronize

    return synchronize(source, root, recursive)


def _inventory_snapshot(source: str) -> dict[str, Any]:
    from .indexer import inventory_snapshot

    return inventory_snapshot(source)


@app.post("/api/hydromet/export-excel")
def export_hydromet_excel(payload: ExcelTableExport, request: Request) -> dict[str, object]:
    from .hydromet_export import export_inventory_excel

    user = _require_user(request)
    if "hydromet" not in user.get("modules", []):
        raise HTTPException(status_code=403, detail="Módulo no autorizado")
    if not payload.headers or len(payload.headers) > 100:
        raise HTTPException(status_code=422, detail="Selecciona al menos una columna válida")
    if len(payload.rows) > 100_000 or any(len(row) != len(payload.headers) for row in payload.rows):
        raise HTTPException(status_code=422, detail="La tabla no tiene una estructura válida")

    return export_inventory_excel(payload.headers, payload.rows, payload.filename)


def _folder_dialog(initial_path: str) -> str:
    selected = choose_directory("Selecciona una carpeta", initial_path)
    return str(selected) if selected else ""


app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/viewer-api", viewer_app, name="viewer-api")
app.mount("/viewer", StaticFiles(directory=FRONTEND_DIR / "viewer", html=True), name="viewer")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio.to_thread
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
    LoginRateLimited,
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


@asynccontextmanager
async def lifespan(_application: FastAPI):
    anyio.to_thread.current_default_thread_limiter().total_tokens = 8
    yield


app = FastAPI(title="Agender", docs_url=None, redoc_url=None, lifespan=lifespan)
viewer_app = LazyAsgiApp("backend.viewer.api", "app")
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60
MAX_REQUEST_BYTES = 50 * 1024 * 1024
MAX_LICENSE_BYTES = 1024 * 1024
MAX_AUTHORITY_KEY_BYTES = 64 * 1024


class RequestSizeLimitMiddleware:
    def __init__(self, application, max_bytes: int):
        self.application = application
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise _RequestTooLarge
            return message

        try:
            await self.application(scope, limited_receive, send)
        except _RequestTooLarge:
            response = Response(
                content='{"detail":"La solicitud excede el tamaño permitido"}',
                status_code=413,
                media_type="application/json",
            )
            await response(scope, receive, send)


class _RequestTooLarge(Exception):
    pass


app.add_middleware(RequestSizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)


async def _read_limited_upload(upload: UploadFile, maximum: int, label: str) -> bytes:
    content = await upload.read(maximum + 1)
    if len(content) > maximum:
        raise HTTPException(status_code=413, detail=f"{label} excede el tamaño permitido")
    return content


@app.middleware("http")
async def enforce_module_access(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return Response(
                    content='{"detail":"La solicitud excede el tamaño permitido"}',
                    status_code=413,
                    media_type="application/json",
                )
        except ValueError:
            return Response(
                content='{"detail":"Content-Length no válido"}',
                status_code=400,
                media_type="application/json",
            )
    path = request.url.path
    required = None
    if path.startswith("/api/local-data"):
        required = "hydromet"
    elif path.startswith("/api/requests"):
        required = "requests"
    elif path.startswith("/api/settings") or path.startswith("/api/select-directory"):
        required = "settings"
    elif path.startswith("/viewer-api"):
        required = "viewer"
    elif path.startswith("/wqreport"):
        required = "report-water-quality"
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
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChangeRequest(BaseModel):
    password: str = Field(min_length=10, max_length=1024)


class UserDataValue(BaseModel):
    value: object


class CloudSyncToggle(BaseModel):
    enabled: bool


class ExcelTableExport(BaseModel):
    filename: str
    headers: list[str]
    rows: list[list[Any]]


class WaterQualityPdfExport(BaseModel):
    reportsHtml: str
    suggestedFileName: str = "Reporte_CA"
    pageHeight: int = 1260


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
    try:
        result = login(credentials.username, credentials.password)
    except LoginRateLimited as error:
        raise HTTPException(
            status_code=429,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after)},
        ) from error
    if not result:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token, user = result
    response.set_cookie(
        "agender_session",
        token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return {"user": user}


@app.post("/api/auth/activate")
async def activate_license(
    response: Response, username: str = Form(...), password: str = Form(...), license: UploadFile = File(...)
) -> dict[str, object]:
    if not 1 <= len(username) <= 128 or not 1 <= len(password) <= 1024:
        raise HTTPException(status_code=422, detail="Usuario o contraseña fuera del tamaño permitido")
    try:
        install_license(await _read_limited_upload(license, MAX_LICENSE_BYTES, "La licencia"), username, password)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        result = login(username, password)
    except LoginRateLimited as error:
        raise HTTPException(
            status_code=429,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after)},
        ) from error
    if not result:
        raise HTTPException(status_code=401, detail="No fue posible activar el usuario")
    token, user = result
    response.set_cookie(
        "agender_session",
        token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return {"user": user}


@app.post("/api/auth/change-password")
def post_change_password(request: Request, response: Response, values: PasswordChangeRequest) -> dict[str, object]:
    try:
        token, user = change_password(request.cookies.get("agender_session"), values.password)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    response.set_cookie(
        "agender_session",
        token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return {"user": user}


@app.put("/api/auth/license")
async def put_current_license(request: Request, license: UploadFile = File(...)) -> dict[str, object]:
    try:
        content = await _read_limited_upload(license, MAX_LICENSE_BYTES, "La licencia")
        user = replace_license(content, request.cookies.get("agender_session"))
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
        content = await _read_limited_upload(key, MAX_AUTHORITY_KEY_BYTES, "La clave de autoridad")
        install_authority_key(content)
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
        content = f"<html><body><h1>No fue posible conectar</h1><p>{html.escape(str(error))}</p></body></html>"
        return Response(content=content, media_type="text/html", status_code=400)
    safe_account = html.escape(str(account))
    content = (
        f"<html><body><h1>Cuenta conectada</h1><p>{safe_account}</p>"
        "<p>Ya puedes volver a Agender.</p></body></html>"
    )
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
        user = _require_user(request)
        result = synchronize_onedrive(user)
        if "requests" in user.get("modules", []):
            from .request_attachments import flush_pending_attachments

            result.update(flush_pending_attachments(user))
        return result
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
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--index-worker"]
    else:
        command = [sys.executable, "-m", "backend", "--index-worker"]
    command.extend(
        [
            "--source",
            source,
            "--root",
            root,
            "--recursive",
            str(recursive).lower(),
        ]
    )
    creation_flags = 0x08000000 if sys.platform == "win32" else 0
    environment = os.environ.copy()
    if getattr(sys, "frozen", False):
        # El trabajador vuelve a ejecutar el mismo binario PyInstaller. Sin un
        # entorno nuevo, el hijo puede intentar reutilizar el bundle ya abierto
        # por el servidor y fallar únicamente en la aplicación instalada.
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    # A redirected Python stdout follows the Windows console code page unless it
    # is pinned explicitly.  The worker prints JSON containing station names and
    # paths, so an accented character could otherwise make the reader thread die
    # before ``subprocess.run`` returns.
    environment["PYTHONIOENCODING"] = "utf-8"
    try:
        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            env=environment,
            timeout=60 * 60,
            creationflags=creation_flags,
        )
        output = process.stdout.decode("utf-8-sig")
        if not output.strip():
            raise ValueError("El indexador no devolvió datos")
        return json.loads(output)
    except subprocess.TimeoutExpired as error:
        raise ValueError("La indexación superó el tiempo máximo permitido") from error
    except (subprocess.CalledProcessError, UnicodeDecodeError, json.JSONDecodeError) as error:
        stderr = getattr(error, "stderr", b"") or b""
        detail = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
        detail = detail or str(error)
        raise ValueError(f"No fue posible actualizar el inventario: {detail.strip()}") from error


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


@app.post("/api/requests/export-excel")
def export_requests_excel(payload: ExcelTableExport, request: Request) -> dict[str, object]:
    from .hydromet_export import export_inventory_excel

    user = _require_user(request)
    if "requests" not in user.get("modules", []):
        raise HTTPException(status_code=403, detail="Módulo no autorizado")
    if not payload.headers or len(payload.headers) > 100:
        raise HTTPException(status_code=422, detail="La tabla no contiene columnas válidas")
    if len(payload.rows) > 100_000 or any(len(row) != len(payload.headers) for row in payload.rows):
        raise HTTPException(status_code=422, detail="La tabla no tiene una estructura válida")

    return export_inventory_excel(payload.headers, payload.rows, payload.filename)


@app.post("/api/requests/{record_id}/attachments")
async def upload_request_attachment(
    record_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    role: str = Form(...),
    pdf: UploadFile = File(...),
) -> dict[str, object]:
    from .request_attachments import MAX_PDF_BYTES, save_request_pdf_local, sync_request_pdf_to_onedrive

    user = _require_user(request)
    content = await _read_limited_upload(pdf, MAX_PDF_BYTES, "El PDF")
    try:
        attachment = await run_in_threadpool(
            save_request_pdf_local,
            user,
            record_id,
            role,
            pdf.filename or "documento.pdf",
            content,
        )
        background_tasks.add_task(sync_request_pdf_to_onedrive, user, attachment)
        return {"attachment": attachment}
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/requests/{record_id}/attachments/{attachment_id}/content")
async def view_request_attachment(record_id: str, attachment_id: str, request: Request) -> Response:
    from .request_attachments import resolve_request_pdf

    user = _require_user(request)
    try:
        path, filename = await run_in_threadpool(resolve_request_pdf, user, record_id, attachment_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@app.delete("/api/requests/{record_id}/documents")
async def delete_request_documents(
    record_id: str, request: Request, background_tasks: BackgroundTasks
) -> dict[str, object]:
    from .request_attachments import delete_request_documents_local, delete_request_documents_onedrive

    user = _require_user(request)
    try:
        deletion = await run_in_threadpool(delete_request_documents_local, user, record_id)
        background_tasks.add_task(delete_request_documents_onedrive, user, deletion)
        return {"deleted": True, "folderDeleted": not deletion["shared"]}
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/requests/{record_id}/folder/open")
async def open_request_documents_folder(record_id: str, request: Request) -> dict[str, object]:
    from .request_attachments import open_request_folder

    user = _require_user(request)
    try:
        path = await run_in_threadpool(open_request_folder, user, record_id)
        return {"opened": True, "path": path}
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/reports/water-quality/export-pdf")
def export_water_quality_pdf(payload: WaterQualityPdfExport, request: Request) -> dict[str, object]:
    from .wqreport_export import export_report_pdf

    user = _require_user(request)
    if "report-water-quality" not in user.get("modules", []):
        raise HTTPException(status_code=403, detail="Módulo no autorizado")
    try:
        return export_report_pdf(
            payload.reportsHtml,
            payload.suggestedFileName,
            payload.pageHeight,
            (FRONTEND_DIR / "wqreport").as_uri() + "/",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _folder_dialog(initial_path: str) -> str:
    selected = choose_directory("Selecciona una carpeta", initial_path)
    return str(selected) if selected else ""


app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
app.mount("/wqreport", StaticFiles(directory=FRONTEND_DIR / "wqreport", html=True), name="wqreport")
app.mount("/viewer-api", viewer_app, name="viewer-api")
app.mount("/viewer", StaticFiles(directory=FRONTEND_DIR / "viewer", html=True), name="viewer")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import read_settings, write_settings
from .indexer import synchronize
from .viewer.api import app as viewer_app
from .security import auth_status, change_password, current_user, generate_license, install_authority_key, install_license, login, logout
from .user_data import read_user_data, write_user_data

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
app = FastAPI(title="Agender", docs_url=None, redoc_url=None)


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
    return await call_next(request)


class PathSettings(BaseModel):
    rawDataPath: str = ""
    qualityDataPath: str = ""
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


class LicenseGenerationRequest(BaseModel):
    licenseId: str
    fullName: str
    username: str
    temporaryPassword: str
    expiresAt: str | None = None
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
async def activate_license(response: Response, username: str = Form(...), password: str = Form(...), license: UploadFile = File(...)) -> dict[str, object]:
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
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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
        return write_settings(settings.model_dump(), user["username"], user["role"] == "admin")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/select-directory")
async def select_directory(request: DirectoryRequest) -> dict[str, str]:
    selected = await run_in_threadpool(_folder_dialog, request.initialPath)
    return {"path": selected}


@app.get("/api/local-data")
async def local_data(request: Request, source: str = Query(default="raw", pattern="^(raw|quality)$")) -> dict[str, object]:
    user = current_user(request.cookies.get("agender_session"))
    settings = read_settings(user["username"], user["role"] == "admin")
    root = settings["rawDataPath" if source == "raw" else "qualityDataPath"]
    recursive = settings["rawIncludeSubfolders" if source == "raw" else "qualityIncludeSubfolders"]
    return await run_in_threadpool(synchronize, source, root, recursive)


def _folder_dialog(initial_path: str) -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(initialdir=initial_path or None, title="Selecciona una carpeta", mustexist=True) or ""
    finally:
        root.destroy()


app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/viewer-api", viewer_app, name="viewer-api")
app.mount("/viewer", StaticFiles(directory=FRONTEND_DIR / "viewer", html=True), name="viewer")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")

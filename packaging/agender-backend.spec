from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

project_root = Path(SPECPATH).parent
polars_data, polars_binaries, polars_hidden = collect_all("polars")
duckdb_data, duckdb_binaries, duckdb_hidden = collect_all("duckdb")
crypto_data, crypto_binaries, crypto_hidden = collect_all("cryptography")
argon_data, argon_binaries, argon_hidden = collect_all("argon2")

analysis = Analysis(
    [str(project_root / "packaging" / "backend_entry.py")],
    pathex=[str(project_root)],
    binaries=[*polars_binaries, *duckdb_binaries, *crypto_binaries, *argon_binaries],
    datas=[
        (str(project_root / "frontend"), "frontend"),
        (str(project_root / "backend" / "data" / "stations.xlsx"), "backend/data"),
        (str(project_root / "backend" / "security" / "license_public_key.pem"), "backend/security"),
        (str(project_root / "src-tauri" / "tauri.conf.json"), "src-tauri"),
        *polars_data,
        *duckdb_data,
        *crypto_data,
        *argon_data,
        *copy_metadata("fastapi"),
        *copy_metadata("pydantic"),
        *copy_metadata("uvicorn"),
    ],
    hiddenimports=[*polars_hidden, *duckdb_hidden, *crypto_hidden, *argon_hidden, "backend.main", "backend.security", "backend.viewer.api", "fastexcel", "pyarrow", "tkinter", "tkinter.filedialog"],
    excludes=["pandas", "numpy", "tkinter.test"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="agender-backend",
    console=False,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="agender-backend",
)

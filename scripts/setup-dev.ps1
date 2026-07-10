$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$virtualenv = Join-Path $projectRoot ".venv"
$python = Join-Path $virtualenv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
  python -m venv $virtualenv
}

& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $projectRoot "backend\requirements-dev.txt")

Write-Host "Entorno listo. Tauri usara automaticamente $python"

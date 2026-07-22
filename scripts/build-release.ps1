param(
  [string]$ExpectedTag = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$privateKeyPath = Join-Path $env:APPDATA "Agender\secrets\updater-private.key"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not $env:TAURI_SIGNING_PRIVATE_KEY) {
  if (-not (Test-Path -LiteralPath $privateKeyPath)) {
    throw "Define TAURI_SIGNING_PRIVATE_KEY o instala la clave en %APPDATA%\Agender\secrets\updater-private.key."
  }
  $env:TAURI_SIGNING_PRIVATE_KEY = Get-Content -LiteralPath $privateKeyPath -Raw
}

if (Test-Path -LiteralPath $venvPython) {
  & $venvPython -m pip install -r (Join-Path $projectRoot "packaging\requirements-build.txt")
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudieron preparar las dependencias de compilación en .venv."
  }
  $env:AGENDER_BUILD_PYTHON = $venvPython
}

& (Join-Path $PSScriptRoot "build-backend.ps1")

Push-Location $projectRoot
try {
  cargo tauri build --ci
  if ($LASTEXITCODE -ne 0) {
    throw "Falló la compilación de Tauri."
  }
} finally {
  Pop-Location
}

& (Join-Path $PSScriptRoot "verify-release.ps1") -ExpectedTag $ExpectedTag

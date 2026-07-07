$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& (Join-Path $PSScriptRoot "build-backend.ps1")
Push-Location $projectRoot
try {
  cargo tauri build
} finally {
  Pop-Location
}

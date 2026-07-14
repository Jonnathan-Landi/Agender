$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distPath = Join-Path $projectRoot "dist\agender-backend"
$resourcePath = Join-Path $projectRoot "src-tauri\resources\backend"
$python = if ($env:AGENDER_BUILD_PYTHON) { $env:AGENDER_BUILD_PYTHON } else { "python" }

Push-Location $projectRoot
try {
  & $python -m PyInstaller --noconfirm --clean "packaging\agender-backend.spec"
  if ($LASTEXITCODE -ne 0) {
    throw "Falló el empaquetado del backend con $python."
  }
  if (Test-Path -LiteralPath $resourcePath) {
    $resolved = (Resolve-Path -LiteralPath $resourcePath).Path
    if (-not $resolved.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar)) {
      throw "La ruta de recursos está fuera del proyecto."
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
  New-Item -ItemType Directory -Path $resourcePath -Force | Out-Null
  Copy-Item -Path (Join-Path $distPath "*") -Destination $resourcePath -Recurse -Force
} finally {
  Pop-Location
}

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

  # Run the same entry point used by the installed application. This catches
  # truncated PyInstaller archives that can otherwise produce a valid-looking
  # installer but fail at startup with "marshal data too short".
  $backendExecutable = Join-Path $resourcePath "agender-backend.exe"
  $inventoryFixture = Join-Path $projectRoot "tests\fixtures\raw"
  $workerOutput = & $backendExecutable --index-worker --source raw --root $inventoryFixture --recursive true
  if ($LASTEXITCODE -ne 0) {
    throw "El backend empaquetado no pudo ejecutar el trabajador de inventario (código $LASTEXITCODE)."
  }
  try {
    $workerResult = ($workerOutput -join "`n") | ConvertFrom-Json
  } catch {
    throw "El backend empaquetado no devolvió un inventario JSON válido."
  }
  if (-not $workerResult.data -or $workerResult.catalogStationCount -lt 1) {
    throw "El backend empaquetado devolvió un inventario de prueba vacío."
  }
} finally {
  Pop-Location
}

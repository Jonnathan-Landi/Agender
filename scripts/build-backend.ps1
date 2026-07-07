$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distPath = Join-Path $projectRoot "dist\agender-backend"
$resourcePath = Join-Path $projectRoot "src-tauri\resources\backend"

Push-Location $projectRoot
try {
  python -m PyInstaller --noconfirm --clean "packaging\agender-backend.spec"
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

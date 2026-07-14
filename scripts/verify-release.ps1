param(
  [string]$ExpectedTag = "",
  [string]$OutputDirectory = "release-artifacts"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tauriConfigPath = Join-Path $projectRoot "src-tauri\tauri.conf.json"
$cargoManifestPath = Join-Path $projectRoot "src-tauri\Cargo.toml"
$bundlePath = Join-Path $projectRoot "src-tauri\target\release\bundle\nsis"
$archivePath = Join-Path $projectRoot "build\agender-backend\PYZ-00.pyz"
$outputPath = Join-Path $projectRoot $OutputDirectory
$python = if ($env:AGENDER_BUILD_PYTHON) { $env:AGENDER_BUILD_PYTHON } else { "python" }

$tauriConfig = Get-Content -LiteralPath $tauriConfigPath -Raw | ConvertFrom-Json
$cargoManifest = Get-Content -LiteralPath $cargoManifestPath -Raw
$cargoVersionMatch = [regex]::Match($cargoManifest, '(?ms)^\[package\].*?^version\s*=\s*"([^"]+)"')
if (-not $cargoVersionMatch.Success) {
  throw "No se pudo leer la versión de src-tauri/Cargo.toml."
}

$version = [string]$tauriConfig.version
$cargoVersion = $cargoVersionMatch.Groups[1].Value
if ($version -ne $cargoVersion) {
  throw "Las versiones no coinciden: tauri.conf.json=$version, Cargo.toml=$cargoVersion."
}
if ($ExpectedTag -and $ExpectedTag -ne "v$version") {
  throw "La etiqueta $ExpectedTag no corresponde a la versión v$version."
}

if (-not (Test-Path -LiteralPath $archivePath)) {
  throw "No existe el archivo del backend empaquetado: $archivePath"
}
$modules = (& $python -m PyInstaller.utils.cliutils.archive_viewer -l $archivePath) -join "`n"
if ($LASTEXITCODE -ne 0) {
  throw "No se pudo inspeccionar el backend empaquetado con $python."
}
foreach ($required in "backend.main", "backend.backup", "backend.config") {
  if ($modules -notmatch "'$([regex]::Escape($required))'") {
    throw "El módulo requerido $required no está incluido en el backend empaquetado."
  }
}

$backendExecutable = Join-Path $projectRoot "src-tauri\resources\backend\agender-backend.exe"
if (-not (Test-Path -LiteralPath $backendExecutable)) {
  throw "No existe el ejecutable del backend empaquetado: $backendExecutable"
}
$backend = Start-Process -FilePath $backendExecutable -ArgumentList "--port", "18765" -PassThru -WindowStyle Hidden
try {
  $ready = $false
  foreach ($attempt in 1..30) {
    if ($backend.HasExited) {
      throw "El backend empaquetado terminó antes de iniciar (código $($backend.ExitCode))."
    }
    try {
      $response = Invoke-WebRequest -Uri "http://127.0.0.1:18765/api/health" -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -eq 200) {
        $ready = $true
        break
      }
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  if (-not $ready) {
    throw "El backend empaquetado no respondió correctamente dentro del tiempo esperado."
  }
} finally {
  if (-not $backend.HasExited) {
    Stop-Process -Id $backend.Id -Force
  }
}

$installers = @(Get-ChildItem -LiteralPath $bundlePath -Filter "Agender_${version}_x64-setup.exe" -File)
if ($installers.Count -ne 1) {
  throw "Se esperaba exactamente un instalador para $version y se encontraron $($installers.Count)."
}
$installer = $installers[0]
if ($installer.Length -lt 1MB) {
  throw "El instalador parece incompleto: solo pesa $($installer.Length) bytes."
}

$signaturePath = "$($installer.FullName).sig"
if (-not (Test-Path -LiteralPath $signaturePath)) {
  throw "Falta la firma del actualizador: $signaturePath"
}
$signature = (Get-Content -LiteralPath $signaturePath -Raw).Trim()
try {
  $decodedSignature = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($signature))
} catch {
  throw "La firma del actualizador no es Base64 válido."
}
if ($decodedSignature -notmatch [regex]::Escape($installer.Name)) {
  throw "La firma no corresponde al instalador $($installer.Name)."
}

if (Test-Path -LiteralPath $outputPath) {
  Remove-Item -LiteralPath $outputPath -Recurse -Force
}
New-Item -ItemType Directory -Path $outputPath | Out-Null
Copy-Item -LiteralPath $installer.FullName -Destination $outputPath
Copy-Item -LiteralPath $signaturePath -Destination $outputPath

$repository = if ($env:GITHUB_REPOSITORY) { $env:GITHUB_REPOSITORY } else { "Jonnathan-Landi/Agender" }
$tag = if ($ExpectedTag) { $ExpectedTag } else { "v$version" }
$downloadUrl = "https://github.com/$repository/releases/download/$tag/$($installer.Name)"
$latest = [ordered]@{
  version = $version
  notes = "Nueva versión de Agender. Consulta los cambios incluidos en esta actualización."
  pub_date = [DateTime]::UtcNow.ToString("o")
  platforms = [ordered]@{
    "windows-x86_64" = [ordered]@{
      signature = $signature
      url = $downloadUrl
    }
  }
}
$latestJson = $latest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText(
  (Join-Path $outputPath "latest.json"),
  $latestJson,
  [Text.UTF8Encoding]::new($false)
)

Write-Host "Release v$version validada. Artefactos listos en $outputPath"

$sdkBinRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
$resourceCompiler = Get-ChildItem -LiteralPath $sdkBinRoot -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
  Sort-Object { [version]$_.Name } -Descending |
  ForEach-Object { Join-Path $_.FullName "x64\rc.exe" } |
  Where-Object { Test-Path -LiteralPath $_ } |
  Select-Object -First 1

if (-not $resourceCompiler) {
  throw "No se encontró RC.EXE. Instala Visual Studio Build Tools con el Windows SDK."
}

$sdkTools = Split-Path -Parent $resourceCompiler
$env:RC = $resourceCompiler
if (($env:PATH -split [IO.Path]::PathSeparator) -notcontains $sdkTools) {
  $env:PATH = "$sdkTools$([IO.Path]::PathSeparator)$env:PATH"
}

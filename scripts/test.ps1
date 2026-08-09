$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
  throw "The Python 3.11 .venv is missing. Run .\scripts\diagnose.ps1 for setup guidance."
}

Push-Location $projectRoot
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
try {
  & $python -m ruff check .
  if ($LASTEXITCODE -ne 0) {
    throw "Ruff checks failed."
  }
  & $python -m pytest
  if ($LASTEXITCODE -ne 0) {
    throw "Pytest failed."
  }
}
finally {
  Pop-Location
}

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$pytest = Join-Path $repositoryRoot ".venv\Scripts\pytest.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "The project Python 3.11 virtual environment is missing."
}

& $python --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$hermesCommand = Get-Command hermes -ErrorAction SilentlyContinue
if ($null -ne $hermesCommand) {
    & $hermesCommand.Source --version
    & $hermesCommand.Source plugins list
} else {
    $managedHermes = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"
    if (-not (Test-Path -LiteralPath $managedHermes -PathType Leaf)) {
        throw "Hermes is not installed in the expected managed location."
    }
    & $managedHermes --version
    & $managedHermes plugins list
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location $repositoryRoot
try {
    & $pytest `
        tests/unit/test_stage13_service_auth.py `
        tests/unit/test_stage13_api_client.py `
        tests/unit/test_stage13_hermes_plugin.py `
        tests/unit/test_stage13_evidence.py `
        tests/unit/test_stage13_idempotency.py `
        -q
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

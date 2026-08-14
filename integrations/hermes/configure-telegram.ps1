[CmdletBinding()]
param(
    [string]$HermesHome = "$env:LOCALAPPDATA\hermes"
)

$ErrorActionPreference = "Stop"
$hermes = Join-Path $HermesHome "hermes-agent\venv\Scripts\hermes.exe"
$python = Join-Path $HermesHome "hermes-agent\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $hermes -PathType Leaf)) {
    throw "Hermes Agent is not installed in the expected managed location."
}

& (Join-Path $PSScriptRoot "install-plugin.ps1") -HermesHome $HermesHome
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# The pinned runtime auto-recovers some defaults when a list contains only a
# plugin. Use its config API to make the list authoritative, suppress its
# recovered Kanban toolset, and opt out of every globally configured MCP server.
& $python (Join-Path $PSScriptRoot "configure_telegram_tools.py") configure
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $hermes config check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python (Join-Path $PSScriptRoot "configure_telegram_tools.py") verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "Telegram tool isolation configured. No Telegram secret was read or printed."

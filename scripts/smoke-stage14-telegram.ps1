[CmdletBinding()]
param(
    [string]$HermesHome = "$env:LOCALAPPDATA\hermes"
)

$ErrorActionPreference = "Stop"
$envFile = Join-Path $HermesHome ".env"
$hermes = Join-Path $HermesHome "hermes-agent\venv\Scripts\hermes.exe"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw "Hermes .env is missing." }
foreach ($line in Get-Content -LiteralPath $envFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
    $name, $value = $trimmed.Split("=", 2)
    if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') { Set-Item -Path "Env:$name" -Value $value }
}

$names = @(
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS", "ZUBEPREDICT_TELEGRAM_OWNER_ID",
    "OPENROUTER_API_KEY", "ZUBEPREDICT_HERMES_SERVICE_KEY"
)
foreach ($name in $names) {
    if ([string]::IsNullOrWhiteSpace((Get-Item "Env:$name" -ErrorAction SilentlyContinue).Value)) {
        throw "Smoke preflight failed: $name is missing."
    }
}
$owner = $env:ZUBEPREDICT_TELEGRAM_OWNER_ID.Trim()
$allowed = @($env:TELEGRAM_ALLOWED_USERS.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($owner -notmatch '^[0-9]{1,20}$' -or $allowed.Count -ne 1 -or $allowed[0] -ne $owner) {
    throw "Smoke preflight failed: owner-only numerical allowlist mismatch."
}
if ($env:TELEGRAM_ALLOW_ALL_USERS -match '^(?i:1|true|yes|on)$' -or
    $env:GATEWAY_ALLOW_ALL_USERS -match '^(?i:1|true|yes|on)$' -or
    -not [string]::IsNullOrWhiteSpace($env:GATEWAY_ALLOWED_USERS)) {
    throw "Smoke preflight failed: a broad Hermes gateway authorisation setting is enabled."
}
$managedDocumentCache = [System.IO.Path]::GetFullPath((Join-Path $HermesHome "cache\documents"))
$configuredDocumentCache = if ([string]::IsNullOrWhiteSpace($env:ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT)) {
    $managedDocumentCache
} else {
    [System.IO.Path]::GetFullPath($env:ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT.Trim())
}
if ($configuredDocumentCache -ine $managedDocumentCache) {
    throw "Smoke preflight failed: ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT does not match Hermes's managed document cache."
}
$toolVerifier = Join-Path $PSScriptRoot "..\integrations\hermes\configure_telegram_tools.py"
& (Join-Path $HermesHome "hermes-agent\venv\Scripts\python.exe") $toolVerifier verify
if ($LASTEXITCODE -ne 0) { throw "Smoke preflight failed: Telegram tools are not isolated." }
$allowedChats = (& $hermes config get gateway.platforms.telegram.extra.allowed_chats | Out-String).Trim()
$guestMode = (& $hermes config get gateway.platforms.telegram.extra.guest_mode | Out-String).Trim()
if ($allowedChats -notmatch '(?<![0-9])0(?![0-9])' -or $guestMode -match '^(?i:true|1|yes|on)$') {
    throw "Smoke preflight failed: Telegram group traffic is not hard-disabled."
}

try {
    $health = Invoke-RestMethod "http://127.0.0.1:8040/health" -TimeoutSec 5
} catch {
    throw "Smoke preflight failed: FastAPI is not available on port 8040."
}
if ($health.status -ne "healthy") { throw "Smoke preflight failed: FastAPI health is not healthy." }
Write-Output "Stage 14 owner-only smoke preflight passed. No secret values were printed."
Write-Output "Continue with the private Telegram conversation checklist in docs\15-STAGE-14-TELEGRAM.md."

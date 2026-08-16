[CmdletBinding()]
param(
    [string]$HermesHome = "$env:LOCALAPPDATA\hermes"
)

$ErrorActionPreference = "Stop"
$envFile = Join-Path $HermesHome ".env"
$hermes = Join-Path $HermesHome "hermes-agent\venv\Scripts\hermes.exe"
$python = Join-Path $HermesHome "hermes-agent\venv\Scripts\python.exe"
$hermesRepository = Join-Path $HermesHome "hermes-agent"
$expectedRevision = "3c27eb6234bf91b8ceee9e9071591b31e9b148cb"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Hermes secret environment file is missing. Follow docs/15-STAGE-14-TELEGRAM.md."
}
if (-not (Test-Path -LiteralPath $hermes -PathType Leaf)) {
    throw "Hermes Agent is not installed in the expected managed location."
}
$actualRevision = (& git -C $hermesRepository rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $expectedRevision) {
    throw "Telegram startup stopped safely: Hermes revision does not match the reviewed pin."
}

# Load simple KEY=VALUE entries only. Values are never emitted.
foreach ($line in Get-Content -LiteralPath $envFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
    $name, $value = $trimmed.Split("=", 2)
    if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
        Set-Item -Path "Env:$name" -Value $value
    }
}

$required = @(
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USERS",
    "ZUBEPREDICT_TELEGRAM_OWNER_ID",
    "OPENROUTER_API_KEY",
    "ZUBEPREDICT_HERMES_KEY_ID",
    "ZUBEPREDICT_HERMES_SERVICE_KEY",
    "ZUBEPREDICT_HERMES_PRINCIPAL_ID"
)
foreach ($name in $required) {
    if ([string]::IsNullOrWhiteSpace((Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue).Value)) {
        throw "Telegram startup stopped safely because $name is missing."
    }
}
$runtimeEnvironment = $env:ZUBEPREDICT_ENV.Trim().ToLowerInvariant()
if ($runtimeEnvironment -notin @("development", "staging", "production")) {
    throw "Telegram startup stopped safely: ZUBEPREDICT_ENV must be explicit."
}

$owner = $env:ZUBEPREDICT_TELEGRAM_OWNER_ID.Trim()
$allowed = @($env:TELEGRAM_ALLOWED_USERS.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($owner -notmatch '^[0-9]{1,20}$' -or $allowed.Count -ne 1 -or $allowed[0] -ne $owner) {
    throw "Telegram startup stopped safely: the numerical allowlist must contain only the owner ID."
}
if ($env:TELEGRAM_ALLOW_ALL_USERS -match '^(?i:1|true|yes|on)$' -or
    $env:GATEWAY_ALLOW_ALL_USERS -match '^(?i:1|true|yes|on)$' -or
    $env:ZUBEPREDICT_TELEGRAM_UNSAFE_ALLOW_ALL -match '^(?i:1|true|yes|on)$') {
    throw "Telegram startup stopped safely: allow-all mode is disabled."
}
if (-not [string]::IsNullOrWhiteSpace($env:GATEWAY_ALLOWED_USERS)) {
    throw "Telegram startup stopped safely: GATEWAY_ALLOWED_USERS must be empty in owner-only mode."
}
$managedDocumentCache = [System.IO.Path]::GetFullPath((Join-Path $HermesHome "cache\documents"))
$configuredDocumentCache = if ([string]::IsNullOrWhiteSpace($env:ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT)) {
    $managedDocumentCache
} else {
    [System.IO.Path]::GetFullPath($env:ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT.Trim())
}
if ($configuredDocumentCache -ine $managedDocumentCache) {
    throw "Telegram startup stopped safely: the attachment root does not match Hermes's managed document cache."
}
$pairingFiles = @(
    (Join-Path $HermesHome "platforms\pairing\telegram-approved.json"),
    (Join-Path $HermesHome "pairing\telegram-approved.json")
)
foreach ($pairingFile in $pairingFiles) {
    if (-not (Test-Path -LiteralPath $pairingFile -PathType Leaf)) { continue }
    $approved = Get-Content -LiteralPath $pairingFile -Raw | ConvertFrom-Json
    $approvedIds = @($approved.PSObject.Properties.Name)
    $unexpected = @($approvedIds | Where-Object { "$_" -ne $owner })
    if ($unexpected.Count -gt 0) {
        throw "Telegram startup stopped safely: revoke non-owner Hermes pairing approvals first."
    }
}
& $python (Join-Path $PSScriptRoot "configure_telegram_tools.py") verify
if ($LASTEXITCODE -ne 0) {
    throw "Telegram startup stopped safely: run integrations\hermes\configure-telegram.ps1 first."
}
$allowedChats = (& $hermes config get gateway.platforms.telegram.extra.allowed_chats | Out-String).Trim()
$guestMode = (& $hermes config get gateway.platforms.telegram.extra.guest_mode | Out-String).Trim()
if ($allowedChats -notmatch '(?<![0-9])0(?![0-9])' -or $guestMode -match '^(?i:true|1|yes|on)$') {
    throw "Telegram startup stopped safely: group traffic is not hard-disabled."
}

Write-Output "Owner-only Telegram configuration passed without printing secrets. Starting Hermes polling gateway."
& $hermes gateway
exit $LASTEXITCODE

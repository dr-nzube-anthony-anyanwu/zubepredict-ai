[CmdletBinding()]
param(
    [switch]$RequireTrivy,
    [switch]$SkipNetworkAudit
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $tracked = @(git ls-files)
    $forbiddenState = @($tracked | Where-Object {
        $_ -match '(^|/)(\.hermes|\.hermes-state|hermes-home|gateway-state)(/|$)' -or
        $_ -match '(^|/)(sessions|conversation[^/]*)\.db$'
    })
    if ($forbiddenState.Count -gt 0) {
        throw "Hermes runtime or conversation state is tracked by Git."
    }

    $secretPatterns = @(
        'sk-or-v1-[A-Za-z0-9_-]{20,}',
        '[0-9]{8,12}:AA[A-Za-z0-9_-]{25,}',
        'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
    )
    foreach ($pattern in $secretPatterns) {
        $matches = @(
            rg --files-with-matches --hidden `
                --glob '!.git/**' --glob '!.venv/**' --glob '!node_modules/**' `
                --glob '!apps/web/.next/**' --glob '!artifacts/**' --glob '!*.lock' `
                -- $pattern . 2>$null
        )
        if ($matches.Count -gt 0) {
            throw "A workspace file matches a prohibited secret pattern. Values were not printed."
        }
    }

    $clientSecretNames = @(
        'OPENROUTER_API_KEY', 'TELEGRAM_BOT_TOKEN', 'SUPABASE_SERVICE_ROLE_KEY',
        'HERMES_SERVICE_KEYS', 'ZUBEPREDICT_HERMES_SERVICE_KEY', 'DATABASE_URL', 'REDIS_URL'
    )
    $clientFiles = @(Get-ChildItem apps\web -Recurse -File | Where-Object {
        $_.FullName -notmatch '\\node_modules\\|\\.next\\|\.env\.example$'
    })
    foreach ($file in $clientFiles) {
        $content = Get-Content -LiteralPath $file.FullName -Raw
        foreach ($name in $clientSecretNames) {
            if ($content -match [regex]::Escape($name)) {
                throw "A prohibited backend secret name appears in frontend source."
            }
        }
    }

    & .\.venv\Scripts\python.exe -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Python dependency consistency check failed." }
    if (-not $SkipNetworkAudit) {
        & .\.venv\Scripts\uv.exe tool run pip-audit --desc
        if ($LASTEXITCODE -ne 0) { throw "Python vulnerability audit failed." }
        Push-Location apps\web
        try {
            npm audit --audit-level=high
            if ($LASTEXITCODE -ne 0) { throw "Frontend dependency audit failed." }
        } finally {
            Pop-Location
        }
    } else {
        Write-Output "Network advisory audit skipped explicitly; run npm audit before deployment."
    }

    $trivy = Get-Command trivy -ErrorAction SilentlyContinue
    if ($null -eq $trivy) {
        if ($RequireTrivy) { throw "Trivy is required but is not installed." }
        Write-Output "Container scan skipped: Trivy is not installed. It is mandatory before deployment."
    } else {
        trivy config --exit-code 1 infrastructure\docker compose.yaml
        if ($LASTEXITCODE -ne 0) { throw "Container configuration scan failed." }
    }
    Write-Output "Stage 17 local security scan passed without printing secrets."
} finally {
    Pop-Location
}

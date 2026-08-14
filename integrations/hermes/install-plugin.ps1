[CmdletBinding()]
param(
    [string]$HermesHome = "$env:LOCALAPPDATA\hermes",
    [switch]$SkipEnable
)

$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot "plugin\zubepredict"
$manifest = Join-Path $source "plugin.yaml"
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    throw "ZubePredict plugin manifest was not found at the expected repository path."
}

$resolvedHome = [System.IO.Path]::GetFullPath($HermesHome)
$pluginsRoot = Join-Path $resolvedHome "plugins"
$destination = Join-Path $pluginsRoot "zubepredict"
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $destination -Recurse -Force

Write-Output "Installed ZubePredict plugin source at: $destination"
if ($SkipEnable) {
    Write-Output "Plugin enable step skipped."
    exit 0
}

$hermesCommand = Get-Command hermes -ErrorAction SilentlyContinue
if ($null -ne $hermesCommand) {
    & $hermesCommand.Source plugins enable zubepredict --no-allow-tool-override
    exit $LASTEXITCODE
}

$managedHermes = Join-Path $resolvedHome "hermes-agent\venv\Scripts\hermes.exe"
if (Test-Path -LiteralPath $managedHermes -PathType Leaf) {
    & $managedHermes plugins enable zubepredict --no-allow-tool-override
    exit $LASTEXITCODE
}

Write-Warning "Plugin copied, but this terminal cannot find Hermes. Open a new terminal and run: hermes plugins enable zubepredict --no-allow-tool-override"

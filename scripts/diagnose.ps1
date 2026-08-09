$ErrorActionPreference = "Continue"

$projectRoot = Split-Path -Parent $PSScriptRoot
$failures = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Write-Pass([string]$message) {
  Write-Host "[PASS] $message" -ForegroundColor Green
}

function Write-WarningMessage([string]$message) {
  $warnings.Add($message)
  Write-Host "[WARN] $message" -ForegroundColor Yellow
}

function Write-Failure([string]$message) {
  $failures.Add($message)
  Write-Host "[FAIL] $message" -ForegroundColor Red
}

function Test-Tool([string]$name, [scriptblock]$versionCommand) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    Write-Failure "$name is not installed or is not available in PATH."
    return $false
  }

  $versionOutput = & $versionCommand 2>&1
  if ($LASTEXITCODE -ne 0) {
    Write-Failure "$name was found but its version command failed."
    return $false
  }

  Write-Pass ($versionOutput | Select-Object -First 1)
  return $true
}

Write-Host "ZubePredict AI environment diagnosis" -ForegroundColor Cyan
Write-Host "Project: $projectRoot"
Write-Host "This check prints configuration status only; it never prints .env contents." -ForegroundColor DarkGray

Push-Location $projectRoot
try {
  Write-Host "`nPython" -ForegroundColor Cyan
  $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Failure "The project .venv is missing. Create it with the installed Python 3.11 interpreter."
  }
  else {
    $pythonVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>&1
    if ($LASTEXITCODE -ne 0) {
      Write-Failure "The .venv Python executable could not run."
    }
    elseif (-not ($pythonVersion -like "3.11.*")) {
      Write-Failure "The .venv uses Python $pythonVersion; ZubePredict is pinned to Python 3.11."
    }
    else {
      Write-Pass ".venv uses Python $pythonVersion."
    }
  }

  Write-Host "`nDeveloper tools" -ForegroundColor Cyan
  $nodeReady = Test-Tool "node" { node --version }
  $npmReady = Test-Tool "npm" { npm --version }
  $gitReady = Test-Tool "git" { git --version }
  $dockerReady = Test-Tool "docker" { docker --version }
  $composeReady = $false
  if ($dockerReady) {
    $composeVersion = docker compose version 2>&1
    if ($LASTEXITCODE -eq 0) {
      Write-Pass ($composeVersion | Select-Object -First 1)
      $composeReady = $true
    }
    else {
      Write-Failure "Docker Compose is unavailable. Install or update Docker Desktop."
    }
  }

  Write-Host "`nPrivate environment file" -ForegroundColor Cyan
  $envPath = Join-Path $projectRoot ".env"
  $envExamplePath = Join-Path $projectRoot ".env.example"
  if (Test-Path -LiteralPath $envPath) {
    Write-Pass ".env exists (contents were not read or printed)."
  }
  elseif (Test-Path -LiteralPath $envExamplePath) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Pass "Created .env from .env.example."
  }
  else {
    Write-Failure "Both .env and .env.example are missing."
  }

  $gitIgnorePath = Join-Path $projectRoot ".gitignore"
  $envIgnoreRulePresent = $false
  if (Test-Path -LiteralPath $gitIgnorePath) {
    $envIgnoreRulePresent = [bool](
      Get-Content -LiteralPath $gitIgnorePath |
        Where-Object { $_ -match '^\s*\.env(?:\s*(?:#.*)?)?$' }
    )
  }
  if ($envIgnoreRulePresent) {
    Write-Pass ".gitignore excludes .env."
  }
  else {
    Write-Failure ".gitignore does not contain a dedicated .env rule."
  }

  if ($gitReady) {
    git -C $projectRoot rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -eq 0) {
      git -C $projectRoot check-ignore -q .env
      if ($LASTEXITCODE -eq 0) {
        Write-Pass "Git confirms that .env is ignored."
      }
      else {
        Write-Failure "Git does not report .env as ignored."
      }
    }
    else {
      Write-WarningMessage "This folder is not currently a Git worktree; the .gitignore rule is present, but git status/check-ignore cannot run until Git is initialised or the repository metadata is restored."
    }
  }

  Write-Host "`nMachine resources" -ForegroundColor Cyan
  try {
    $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $ramGb = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
    Write-Pass "Windows reports $ramGb GB of physical RAM."
  }
  catch {
    Write-WarningMessage "Windows RAM information could not be read: $($_.Exception.Message)"
  }

  $projectDriveName = (Get-Item -LiteralPath $projectRoot).PSDrive.Name
  $projectDrive = Get-PSDrive -Name $projectDriveName -ErrorAction SilentlyContinue
  if ($projectDrive) {
    $freeGb = [math]::Round($projectDrive.Free / 1GB, 1)
    if ($freeGb -lt 10) {
      Write-WarningMessage "Drive $projectDriveName has only $freeGb GB free; Docker/ML builds may run out of space."
    }
    else {
      Write-Pass "Drive $projectDriveName has $freeGb GB free."
    }
  }
  else {
    Write-WarningMessage "Free disk space for the project drive could not be determined."
  }

  Write-Host "`nDocker and Redis smoke check" -ForegroundColor Cyan
  if ($dockerReady -and $composeReady) {
    $dockerMemory = docker info --format "{{.MemTotal}}" 2>&1
    if ($LASTEXITCODE -ne 0) {
      Write-Failure "Docker Desktop is installed but its engine is unavailable. Start Docker Desktop and rerun this script."
    }
    else {
      $dockerMemoryGb = [math]::Round(([double]$dockerMemory) / 1GB, 1)
      if ($dockerMemoryGb -lt 6) {
        Write-WarningMessage "Docker has $dockerMemoryGb GB memory available; assign at least 6 GB for the ML image when practical."
      }
      else {
        Write-Pass "Docker engine is running with $dockerMemoryGb GB memory available."
      }

      $redisCheck = docker compose run --rm --no-deps redis redis-server --version 2>&1
      if ($LASTEXITCODE -eq 0) {
        Write-Pass "Docker Compose started and removed a Redis smoke-test container successfully."
      }
      else {
        Write-Failure "The Redis Compose smoke test failed. Review Docker Desktop and run 'docker compose config'."
      }
    }
  }

  Write-Host "`nDiagnosis summary" -ForegroundColor Cyan
  Write-Host "Failures: $($failures.Count) | Warnings: $($warnings.Count)"
  if ($failures.Count -gt 0) {
    Write-Host "Resolve the failures above, then rerun .\scripts\diagnose.ps1." -ForegroundColor Red
    exit 1
  }

  Write-Host "Stage 0 environment checks passed." -ForegroundColor Green
  exit 0
}
finally {
  Pop-Location
}

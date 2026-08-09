$ErrorActionPreference = "Stop"
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example" -ForegroundColor Green
}
docker compose up --build


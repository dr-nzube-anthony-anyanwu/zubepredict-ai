$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$containerName = "zubepredict-supabase-migration-check"
$bootstrap = Join-Path $projectRoot "tests\fixtures\supabase_bootstrap.sql"
$migration = Join-Path $projectRoot "infrastructure\supabase\001_initial_schema.sql"
$stage3Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260809003207_secure_dataset_lifecycle.sql"
$stage4Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260809013027_intent_target_task_decisions.sql"
$stage7Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260809025738_async_experiment_jobs.sql"
$stage12Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260809045626_langgraph_workflow_checkpoints.sql"
$stage14Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260812132803_stage14_telegram_channel_state.sql"
$stage15Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260814124755_stage15_unified_dashboard_linking.sql"
$stage16Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260814165227_stage16_versioned_report_artifacts.sql"
$stage17Migration = Join-Path $projectRoot `
  "infrastructure\supabase\supabase\migrations\20260815002438_stage17_security_quotas_retention.sql"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is required for the disposable Supabase migration syntax check."
}

$existing = docker ps -a --filter "name=^/$containerName$" --format "{{.ID}}"
if ($existing) {
  throw "A container named $containerName already exists. Remove or rename it before retrying."
}

try {
  $containerId = docker run --detach --rm --name $containerName `
    --env POSTGRES_PASSWORD=local-stage2-check `
    postgres:15-alpine
  if ($LASTEXITCODE -ne 0 -or -not $containerId) {
    throw "The disposable PostgreSQL container could not start."
  }

  $ready = $false
  for ($attempt = 1; $attempt -le 30; $attempt++) {
    docker exec $containerName pg_isready -U postgres *> $null
    if ($LASTEXITCODE -eq 0) {
      $ready = $true
      break
    }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) {
    throw "The disposable PostgreSQL container did not become ready."
  }

  docker cp $bootstrap "${containerName}:/tmp/supabase_bootstrap.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Supabase bootstrap fixture." }
  docker cp $migration "${containerName}:/tmp/001_initial_schema.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 2 migration." }
  docker cp $stage3Migration "${containerName}:/tmp/stage3_secure_dataset_lifecycle.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 3 migration." }
  docker cp $stage4Migration "${containerName}:/tmp/stage4_intent_target_task_decisions.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 4 migration." }
  docker cp $stage7Migration "${containerName}:/tmp/stage7_async_experiment_jobs.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 7 migration." }
  docker cp $stage12Migration "${containerName}:/tmp/stage12_langgraph_checkpoints.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 12 migration." }
  docker cp $stage14Migration "${containerName}:/tmp/stage14_telegram_channel_state.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 14 migration." }
  docker cp $stage15Migration "${containerName}:/tmp/stage15_unified_dashboard_linking.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 15 migration." }
  docker cp $stage16Migration "${containerName}:/tmp/stage16_versioned_report_artifacts.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 16 migration." }
  docker cp $stage17Migration "${containerName}:/tmp/stage17_security_quotas_retention.sql" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Could not copy the Stage 17 migration." }

  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/supabase_bootstrap.sql *> $null
  if ($LASTEXITCODE -ne 0) { throw "The Supabase bootstrap fixture failed." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/001_initial_schema.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 2 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage3_secure_dataset_lifecycle.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 3 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage4_intent_target_task_decisions.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 4 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage7_async_experiment_jobs.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 7 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage12_langgraph_checkpoints.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 12 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage14_telegram_channel_state.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 14 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage15_unified_dashboard_linking.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 15 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage16_versioned_report_artifacts.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 16 migration failed PostgreSQL validation." }
  docker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 `
    -f /tmp/stage17_security_quotas_retention.sql
  if ($LASTEXITCODE -ne 0) { throw "The Stage 17 migration failed PostgreSQL validation." }

  $policyCount = docker exec $containerName psql -U postgres -Atc `
    "select count(*) from pg_policies where schemaname in ('public', 'storage');"
  if ($LASTEXITCODE -ne 0 -or [int]$policyCount -lt 12) {
    throw "Expected Stage 2 RLS policies were not created."
  }

  $unprotectedPublicTables = docker exec $containerName psql -U postgres -Atc `
    "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity;"
  if ($LASTEXITCODE -ne 0 -or [int]$unprotectedPublicTables -ne 0) {
    throw "Every public table must have row-level security enabled."
  }

  $reportIntegrityColumnCount = docker exec $containerName psql -U postgres -Atc `
    "select count(*) from information_schema.columns where table_schema = 'public' and table_name = 'reports' and column_name in ('report_version','filename','content_type','size_bytes','sha256','evidence_hash','integrity_metadata');"
  if ($LASTEXITCODE -ne 0 -or [int]$reportIntegrityColumnCount -ne 7) {
    throw "Expected Stage 16 report integrity columns were not created."
  }

  $stage17ColumnCount = docker exec $containerName psql -U postgres -Atc `
    "select count(*) from information_schema.columns where table_schema = 'public' and ((table_name = 'datasets' and column_name in ('privacy_attested_at','deidentified_confirmed','consent_scope')) or (table_name = 'reports' and column_name in ('retention_status','retention_expires_at','deleted_at')));"
  if ($LASTEXITCODE -ne 0 -or [int]$stage17ColumnCount -ne 6) {
    throw "Expected Stage 17 privacy and retention columns were not created."
  }

  $stage17TriggerCount = docker exec $containerName psql -U postgres -Atc `
    "select count(distinct trigger_name) from information_schema.triggers where trigger_name in ('enforce_dataset_storage_quota','enforce_experiment_concurrency_quota');"
  if ($LASTEXITCODE -ne 0 -or [int]$stage17TriggerCount -ne 2) {
    throw "Expected Stage 17 atomic resource quota triggers were not created."
  }

  Write-Host "Supabase migrations through Stage 17 passed with $policyCount RLS policies, $reportIntegrityColumnCount report integrity columns, and $stage17ColumnCount privacy/retention columns." `
    -ForegroundColor Green
}
finally {
  $remaining = docker ps -a --filter "name=^/$containerName$" --format "{{.ID}}"
  if ($remaining) {
    docker rm --force $containerName *> $null
  }
}

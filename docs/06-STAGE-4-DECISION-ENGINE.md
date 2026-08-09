# Stage 4: Intent, Target, and Task Decisions

Stage 4 makes task selection explainable and deterministic. It classifies
binary, multiclass, regression, clustering, anomaly, and forecasting intent;
scores plausible targets; blocks unsuitable targets; and asks a focused
question when evidence is ambiguous. Optional Hermes suggestions remain
presentation-only and cannot silently change the deterministic result.

## Apply the Stage 4 migration once

Open Supabase **SQL Editor**, paste the complete contents of:

```text
infrastructure/supabase/supabase/migrations/20260809013027_intent_target_task_decisions.sql
```

Run it once after the Stage 3 migration. Do not rerun it after it succeeds. It
adds decision evidence, source, version, timestamps, and task constraints. It
also prevents authenticated clients from updating experiment decisions
directly; decision mutations use the server-only service role and audit log.

## Deterministic decision contract

`detect_task` returns the selected task and target alongside structured
evidence, ranked target candidates, confidence reasons, a deterministic
evidence hash, and an exact clarification question when needed.

Target suitability rejects identifiers, constants, empty targets, and targets
with more than half their values missing. Forecasting additionally requires a
credible target and a time-order column. An optional `TaskSuggestion` can be
attached for a Hermes explanation, but `suggestion_used` remains false.

## Confirmed overrides

All decision endpoints require `Authorization: Bearer <Supabase access token>`.

- `POST /api/v1/decisions/experiments/{id}/override` requires an explicit
  `confirmed_by_user: true`, a 10–1000 character rationale, a valid task, and a
  target present in the finalized dataset schema for supervised tasks.
- `GET /api/v1/decisions/experiments/{id}/history` returns the owned audit
  history for that experiment.

Overrides use optimistic decision versions, store the previous and confirmed
decision as evidence, set confidence to 1.0 to represent user confirmation,
and record both the request and successful application. Clustering and anomaly
detection reject target columns. A user cannot access another user's decision.

## Verification

Validate all database migrations in disposable PostgreSQL:

```powershell
.\scripts\validate-supabase-migration.ps1
```

After applying the Stage 4 migration, run the disposable live test:

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\python.exe scripts\smoke_supabase_stage4.py
```

The test creates temporary users and metadata, confirms and audits an override,
checks cross-user isolation and direct-update denial, and removes everything it
created. It never prints credentials or access tokens.

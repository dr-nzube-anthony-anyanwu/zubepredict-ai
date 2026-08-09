# ZubePredict AI Implementation Record

This file is the durable engineering history and Codex handoff record for ZubePredict AI.
It explains what has been implemented, why important decisions were made, what went wrong,
what was corrected, what is verified, and where work stopped.

It deliberately excludes passwords, API keys, access tokens, login links, database
credentials, private URLs, user data, and `.env` values.

## Instructions for every future Codex session

Before changing this repository:

1. Read `README.md` completely.
2. Read this `IMPLEMENTATION.md` completely.
3. Inspect the files directly related to the requested change.
4. Treat Stages 0 through 12 as an existing working baseline; do not rebuild them from
   scratch or silently weaken their tests.
5. Preserve Python 3.11, backend port 8040, and frontend port 3040 unless the owner
   explicitly requests a change.
6. Never print or copy `.env` values, service-role credentials, Supabase database
   passwords, CLI login links, Telegram tokens, or provider keys.
7. Use `infrastructure/supabase` as the Supabase CLI work directory.
8. Keep deterministic Python responsible for data processing, task decisions, training,
   metrics, evaluation, artifacts, and evidence. LLMs may explain verified evidence but
   must not invent or modify it.
9. Run checks proportional to the change and report the actual results.
10. Stop all temporary services/containers after verification unless the owner asks to
    leave them running.
11. Update this file after every material stage, correction, migration, architecture
    decision, or newly discovered limitation.

## Current project status

Last updated: 2026-08-09.

Current stopping point: **Stage 12 is complete. Stage 13 has not started.**

The implemented product is a working backend/ML/orchestration foundation with a starter
Next.js interface. The full dashboard, hardened Hermes layer, Telegram workflow, reporting,
production security controls, and deployment remain future stages.

Current runtime state at the last verification:

- No API process intentionally left running.
- No frontend process intentionally left running.
- No Docker containers intentionally left running.
- The local project `.venv` reports Python 3.11.0.
- API and worker Docker images build successfully.
- The hosted Supabase database contains the Stage 12 checkpoint tables.
- The Supabase project is linked locally under `infrastructure/supabase`.
- Supabase migration history is aligned: all four local numbered versions are recorded on
  the linked remote project.

Latest complete regression evidence:

- 134 pytest tests passed after Stage 12.
- Ruff passed.
- mypy passed across `packages` and `apps` (44 source files at that point).
- Next.js 15.5.23 production build passed.
- API and worker Docker builds passed.
- A disposable Docker API runtime reported Python 3.11.15 and imported the Stage 12
  workflow successfully.
- The full SQL migration chain passed against disposable PostgreSQL with 14 RLS policies.
- Read-only hosted Supabase checks confirmed the Stage 3, 4, 7, and 12 schema.

Warnings seen during otherwise successful verification:

- A LangGraph serializer pending-deprecation warning.
- A Starlette TestClient/httpx deprecation warning.
- SHAP/Matplotlib pending-deprecation warnings.
- A joblib physical-core detection warning on Windows.

These warnings did not fail tests, but future dependency work should reassess them rather
than suppressing them blindly.

## Non-negotiable engineering invariants

- Python runtime and `.venv`: Python 3.11, not Python 3.13.
- Backend/API port: 8040.
- Frontend port: 3040.
- Redis development port: 6379.
- Core ML operations must be deterministic where practical and record the configured seed.
- Preprocessing must be fitted only on training folds.
- Every advanced candidate must be compared with an appropriate baseline.
- A model must not be called “best” without the metric and validation design.
- Ambiguous task or target decisions must pause for clarification.
- User overrides must be explicit, validated, versioned, and auditable.
- Cross-user data access must be prevented by ownership checks and RLS.
- Uploaded files are untrusted and must be bounded and validated.
- Queue messages contain identifiers only—not data, secrets, tokens, or local paths.
- Model artifacts must not use unsafe untrusted pickle deserialization.
- LLM output is untrusted narrative and cannot alter stored evidence or metrics.
- Secrets belong only in ignored environment configuration and provider dashboards.

## Current architecture

### Services

| Component | Location | Responsibility |
|---|---|---|
| FastAPI | `apps/api/zubepredict_api` | HTTP API, Auth boundary, synchronous analysis, job control |
| Worker | `apps/worker` | Dataset retrieval, graph execution, ML, artifacts, job state |
| Next.js | `apps/web` | Current starter interface; full dashboard is future Stage 15 |
| Telegram | `apps/telegram_bot` | Early command/polling foundation only |
| Core package | `packages/zubepredict_core` | Data, ML, repositories, schemas, decisions, workflows |
| Redis | Docker/local | Dramatiq broker and per-experiment lock coordination |
| Supabase | Hosted | Auth, Postgres, RLS, private Storage, checkpoints |

### Request and job flow

1. An authenticated user owns a project and finalized dataset.
2. `POST /api/v1/experiments/jobs` validates ownership and an idempotency key.
3. The API creates one experiment job through the trusted repository.
4. Dramatiq receives only `experiment_id`, `owner_id`, and `job_id`.
5. The worker atomically claims a queued job.
6. The worker downloads the owned dataset from private Supabase Storage and verifies its
   SHA-256 fingerprint and file signature.
7. LangGraph profiles, decides, validates the plan, optionally interrupts, trains,
   persists, and finalizes.
8. Progress and summaries are stored on the experiment; model rows and artifacts are
   stored separately.
9. If clarification is required, the API resumes the same job and graph thread.
10. Completed graph state short-circuits repeat invocation so training is not duplicated.

### LangGraph route

```text
START
  -> profile
  -> decide
      -> clarify -> decide    (when task/target is ambiguous)
      -> plan
          -> clarify -> decide (when forecast configuration is incomplete)
          -> train
          -> finalize
          -> END
```

The graph state contains JSON-safe identifiers, configuration, decisions, plans,
clarifications, and bounded result summaries. DataFrames and fitted model objects are not
stored inside graph state.

## Persistence and security design

### Repository boundary

Core code uses repository records/contracts rather than allowing ML modules to depend
directly on Supabase. Authenticated clients operate with user sessions and RLS. Trusted API
and worker operations use the service-role client, which must never be available to the
browser.

### Supabase tables

The base schema covers:

- `projects`
- `datasets`
- `experiments`
- `model_runs`
- `reports`
- `audit_logs`
- private Storage bucket configuration and policies

Stage 12 adds:

- `workflow_checkpoints`
- `workflow_checkpoint_writes`

Checkpoint tables are owner-scoped and server-only. They have RLS enabled, explicit
service-role grants, and no `anon` or `authenticated` grants because graph internals can
contain routing state that should not be exposed to browser clients.

### Migration files

The current ordered migration history is:

| Version | Purpose |
|---|---|
| `20260809003207` | Secure dataset lifecycle metadata and permissions |
| `20260809013027` | Intent/target decisions and override evidence |
| `20260809025738` | Durable asynchronous experiment jobs |
| `20260809045626` | LangGraph checkpoints and pending writes |

The base schema is intentionally stored separately as
`infrastructure/supabase/001_initial_schema.sql`. A new project must execute that file once
in the Supabase SQL Editor before applying the numbered CLI migrations.

Migration files live under:

```text
infrastructure/supabase/supabase/migrations
```

Therefore CLI commands issued from the repository root must use:

```powershell
--workdir infrastructure/supabase
```

## Stage-by-stage implementation history

### Stage 0 — environment diagnosis

Implemented and verified the Windows environment diagnostic in `scripts/diagnose.ps1`.
It checks Python, Node, npm, Git, Docker, Compose, `.env` presence/ignore status, RAM, disk,
Docker memory, and a disposable Redis smoke container without printing environment values.

Key decision: the repository must use the installed Python 3.11 interpreter. An existing
Python 3.13 environment is not acceptable because several ML dependencies and the project
contract target 3.11.

### Stage 1 — starter stabilization

Stabilized the FastAPI service, frontend build, Python dependencies, Docker workflow, and
baseline tests. Backend was standardized on port 8040 and frontend on 3040. Docker uses
`python:3.11-slim`; `pyproject.toml` rejects Python 3.13 with `>=3.11,<3.13`.

The frontend remains separate from Compose. `compose.yaml` contains Redis, API, and worker.

### Stage 2 — Supabase foundation

Added authenticated and service-role repository adapters, typed records, ownership
boundaries, base Postgres schema, RLS, private Storage configuration, integration mocks,
and a live two-user isolation smoke script.

Security decision: service-role credentials remain in trusted server configuration only.

### Stage 3 — secure dataset lifecycle

Added signed upload intents, safe finalization, signature/extension checks, bounded
streaming, metadata inspection, SHA-256 fingerprints, private UUID paths, retention state,
and audited deletion. CSV, Excel, and Parquet are supported within configured limits.

### Stage 4 — task decision engine

Added deterministic task and target evidence, semantic hints, candidate suitability,
confidence reasons, ambiguity handling, and explicit task overrides. Overrides require user
confirmation, validate targets, increment a decision version, and create audit events.

### Stage 5 — data-quality and leakage guardian

Added structured blocking errors and warnings for identifiers, constants, quasi-constants,
duplicates, missingness, cardinality, suspicious dates, grouped entities, temporal order,
target duplicates, proxy leakage, post-outcome names, and forbidden features. Risky feature
use requires explicit acknowledgement IDs.

### Stage 6 — supervised tournament

Added candidate planning, leakage-safe pipelines, classification/regression validation,
fold evidence, out-of-fold predictions, calibration/threshold support, confidence
intervals, optional advanced libraries, candidate-failure isolation, and safe winner
artifact creation after selection.

### Stage 7 — asynchronous experiment jobs

Moved expensive work behind Redis/Dramatiq. Added idempotency keys, database claims,
heartbeats, progress, cancellation, bounded retry/backoff, graceful shutdown behavior,
stale-job recovery, and model-run replacement by job. The API stays responsive while the
worker trains.

The queue contract intentionally remains exactly three identifiers.

### Stage 8 — clustering and anomaly detection

Added unsupervised suitability checks, mixed preprocessing, clustering-family and
cluster-count comparison, internal validation, stability evidence, multiple anomaly
detectors, and consensus evidence. Output language avoids presenting clusters as true
labels.

### Stage 9 — time-series forecasting

Added explicit forecast contracts, time sorting, gap/duplicate handling, rolling-origin
validation, baselines, bounded statistical models, and supported intervals. Missing or
unsafe forecast choices produce clarification rather than inference by guesswork.

### Stage 10 — tuning and compute budgets

Added deterministic Optuna tuning, pruning, bounded trials/time, dataset-aware reduction,
per-user/per-experiment limits, and untuned-baseline retention. The worker validates
configuration types and positive limits.

### Stage 11 — explanations and error analysis

Added structured global/local explanations, bounded SHAP use, diagnostic plot data,
learning curves, and cautious segment error analysis. Evidence is persisted privately,
with artifact hashes, before any future LLM narrative.

### Stage 12 — LangGraph orchestration

Added:

- Typed `WorkflowState`.
- Explicit deterministic nodes and conditional edges.
- Bounded two-attempt retries for safe pre-training transient failures.
- Cancellation checks around work boundaries.
- LangGraph `interrupt()` clarification.
- Supabase checkpoint/pending-write saver.
- Authenticated resume API.
- Same-thread and same-job resume semantics.
- Completed-checkpoint short-circuit.
- Model-run replacement for retry idempotency.
- Migration validation and Stage 12 workflow tests.

Training and persistence remain one deliberate idempotent boundary: artifacts and model-run
evidence are persisted before the graph records that node as completed. Retries upsert
artifacts and replace model rows for the same job.

## Corrections, mistakes, and lessons learned

This section is intentionally candid so future work does not repeat earlier mistakes.

### Python interpreter mismatch

Problem: the machine also had Python 3.13, while the project required 3.11.

Correction: recreate and verify `.venv` with Python 3.11, constrain the project to
`>=3.11,<3.13`, and use `python:3.11-slim` in Docker. Changing dependency metadata alone
does not change the interpreter inside an existing virtual environment.

### Port inconsistency

Problem: starter defaults were not consistently aligned with the desired local ports.

Correction: API, environment examples, Compose, and commands now use 8040; Next.js `dev`
and `start` use 3040. Future changes must preserve those ports unless explicitly requested.

### Processes left running during verification

Problem: development services used for checking could interfere with the owner's terminal
commands.

Correction: stop API/frontend/Compose services after verification and explicitly confirm
that nothing remains running. Docker image builds do not require leaving containers up.

### Docker frontend assumption

Problem: a verification command attempted to build a Compose service named `web`.

Cause: the frontend exists in the repository but is not declared in `compose.yaml`.

Correction: use `docker compose build api worker` for Python services and run
`npm run build` from `apps/web` for the frontend. Do not claim `docker compose up` starts
the frontend.

### Browser-extension hydration warning

Problem: Next.js reported a hydration mismatch on `<body>` attributes including Grammarly
and shortcut-listener markers.

Cause: a browser extension modified server-rendered HTML before React hydrated.

Correction: add `suppressHydrationWarning` to the root `<body>`. This is appropriate only
for the known extension-injected attributes; genuine application hydration mismatches must
still be diagnosed.

### Supabase was configured later than the code stages

Problem: persistence work initially proceeded before the hosted Supabase setup was fully
available.

Correction: complete Auth/database/storage setup, then run live owner-isolation and schema
checks. Future database stages should distinguish local SQL validation from hosted
verification.

### Supabase project-ref error

Problem: `npx supabase db push` at the repository root returned “Cannot find project ref.”

Causes:

- The folder had not yet been linked with the Supabase CLI.
- Migration files use the non-root CLI work directory `infrastructure/supabase`.

Correction: log in, link with `--workdir infrastructure/supabase`, and include that workdir
on every migration command.

### Existing schema was missing from migration history

Problem: the first linked dry run proposed Stage 3, 4, 7, and 12, even though Stage 3, 4,
and 7 had already been applied manually.

Risk: replaying older non-idempotent `ALTER TABLE` and constraint statements could fail.

Correction:

1. Select No at the push prompt.
2. Verify the older remote columns with read-only service queries.
3. Mark only confirmed Stage 3, 4, and 7 versions as `applied` using
   `supabase migration repair`.
4. Dry-run again and apply only the Stage 12 migration.
5. Verify the Stage 12 tables with read-only hosted queries.

Lesson: migration history and physical schema are distinct. Never repair history without
first confirming that the corresponding schema actually exists.

### Stage 12 implementation corrections

During Stage 12, static and behavioral checks found several issues before completion:

- LangGraph node typing needed explicit typing/casts compatible with the installed version.
- Formatting issues were corrected rather than ignored.
- The custom checkpoint saver channel-version generic was corrected from `str` to `int`,
  matching the base saver's default monotonically increasing version behavior.
- Completed checkpoint state was checked before invocation to prevent retraining.
- An obsolete unreachable copy of the former linear worker pipeline was removed after the
  graph adapter was working.
- Resume validation was tightened so supervised tasks require a confirmed target present in
  the validated schema and unsupervised tasks reject targets.
- A cross-worker fake-Supabase test was added to prove checkpoints survive saver/graph
  reconstruction without duplicate training.

Lesson: orchestration should wrap working deterministic functions rather than rewrite their
math, and durability must be tested across reconstructed worker instances.

## API contracts worth preserving

### Job creation

- Route: `POST /api/v1/experiments/jobs`.
- Requires authenticated owner, owned project/dataset, active dataset, and
  `Idempotency-Key`.
- A repeated key returns the existing experiment instead of creating another job.

### Queue actor

```python
run_experiment(experiment_id: str, owner_id: str, job_id: str)
```

Do not add file content, tokens, repository objects, local paths, or DataFrames to this
signature.

### Clarification resume

- Route: `POST /api/v1/experiments/{experiment_id}/resume`.
- Only valid from `needs_clarification`.
- Uses the original job ID and experiment/thread ID.
- Task clarification requires `confirmed_by_user: true`.
- Completed/cancelled/failed/already-queued jobs cannot be resumed through this route.

### Cancellation

- Queued or clarification jobs can become cancelled immediately.
- Active work records a cancellation request; worker checks terminate safely.
- Completed, failed, and cancelled jobs are terminal for cancellation purposes.

## Testing strategy

### Fast local gate

```powershell
.\scripts\test.ps1
```

### Complete backend gate

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe packages apps
.\.venv\Scripts\pytest.exe -q
```

### Frontend gate

```powershell
cd apps\web
npm run build
```

### Docker gate

```powershell
docker compose build api worker
```

### Migration gate

```powershell
.\scripts\validate-supabase-migration.ps1
```

This creates a disposable PostgreSQL container, applies the base and staged migrations,
checks RLS policy creation, and removes the container in cleanup.

### Hosted Supabase smoke tests

Live smoke scripts create temporary Auth users and data and attempt cleanup. They must run
only against the intended development project and should never print credentials.

## Configuration and secrets boundary

Safe to document:

- Environment variable names.
- Ports.
- Public route paths.
- Bucket names when they are generic configuration.
- Migration versions and table names.
- Non-secret project architecture.

Never place here:

- Values from `.env`.
- Supabase service-role or secret keys.
- Supabase database passwords.
- CLI login/session URLs.
- User JWTs or refresh tokens.
- OpenRouter keys.
- Telegram tokens.
- Private dataset contents or signed Storage URLs.

If a future session needs a secret, ask the owner to place it directly in `.env` or the
provider dashboard. Do not ask them to paste it into chat.

## Known limitations at the stopping point

- The frontend is a starter landing page, not the full project/data/experiment dashboard.
- Supabase Auth is used by API flows, but the current frontend has no complete Auth UI.
- The Telegram bot contains starter commands/placeholders and does not implement the secure
  Stage 14 workflow.
- The LLM abstraction exists, but Stage 13 structured validation, injection resistance,
  provider retry/fallback policy, evidence IDs, and budgets are not implemented yet.
- Reporting tables exist, but complete HTML/PDF/model-card generation is Stage 16.
- Production rate limiting, storage/job quotas, automatic retention execution, dependency
  scanning, and administrative controls remain Stage 17.
- Render configuration is a restricted demonstration starting point; continuous reliable
  worker hosting and production monitoring are not complete.
- No claim has been made that model outputs are suitable for high-stakes decisions.
- This folder was observed without usable Git worktree metadata during earlier diagnostics;
  confirm repository/version-control state before attempting commits, branches, or pushes.

## Next planned work

The next roadmap item is **Stage 13 — Nous Hermes**. Do not start it merely because this
file mentions it; wait for explicit owner approval.

Stage 13 contract:

- Preserve `template`, `openrouter`, and `ollama` providers.
- Accept only validated structured language outputs.
- Retry malformed output once, then fall back safely.
- Treat dataset cell text as untrusted data, never instructions.
- Bind narratives to verified evidence hashes/IDs.
- Add request/token budgets and graceful provider failure.
- Document optional local Hermes Q4 use for a 16 GB Windows machine without making it
  mandatory.
- Prove the language layer cannot alter verified metrics.

Later stages remain:

- Stage 14: secure Telegram workflow.
- Stage 15: authenticated Next.js dashboard.
- Stage 16: reporting and reproducibility exports.
- Stage 17: security, quotas, and retention hardening.
- Stage 18: restricted demonstration deployment.

## Handoff checklist

At the beginning of future work, establish the baseline with:

```powershell
Get-Location
.\.venv\Scripts\python.exe --version
docker compose config --services
.\.venv\Scripts\pytest.exe -q
```

Then inspect only the relevant code and confirm the owner’s requested stage/scope. Do not
start services unnecessarily. If services are needed for verification, stop them before
handoff unless instructed otherwise.

At the end of future work, update these fields:

- `Last updated` and `Current stopping point`.
- Latest verified test/build counts.
- Stage history or correction log.
- Migration list and hosted application status when changed.
- Known limitations and next planned work.

The goal is that a future Codex session can understand the project from `README.md` and
this file, verify the facts against the repository, and continue without repeating old
mistakes or breaking completed stages.

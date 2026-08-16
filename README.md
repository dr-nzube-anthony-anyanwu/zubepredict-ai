# ZubePredict AI

ZubePredict AI is an evidence-driven, stage-built data-science platform. It accepts
tabular datasets, validates and profiles them, determines an appropriate machine-learning
task, blocks unsafe leakage patterns, compares suitable models, persists reproducible
evidence, and pauses for human clarification when a decision cannot be made safely.

The repository currently implements Stages 0 through 17 of the project roadmap. The authenticated
Next.js dashboard and Hermes Telegram agent share the same owner-scoped projects, datasets,
experiments, evidence and reports. Stage 16 generates one authoritative, versioned artifact bundle
for every channel. Stage 17 adds distributed quotas, privacy attestation, retention controls,
security logging and a production security gate. Stages 14 and 15 passed their private owner smoke
tests; the complete Stage 17 automated regression passed locally. The Stage 17 migration is applied
and physically verified on the hosted development database. No public deployment has been performed.

For the engineering history, corrections, current stopping point, and instructions for a
future Codex session, read [IMPLEMENTATION.md](IMPLEMENTATION.md) before making changes.

## Important use warning

ZubePredict AI is an engineering and research platform. Its results must not be used as
the sole basis for high-stakes medical, financial, employment, insurance, legal, or public
safety decisions. A real deployment requires domain validation, fairness testing,
monitoring, privacy controls, security review, and accountable human oversight.

## Current capabilities

### Data ingestion and lifecycle

- CSV, XLS, XLSX, and Parquet validation and loading.
- Streaming upload-size enforcement and bounded previews.
- File signature, extension, MIME-type, row-count, and column-count checks.
- SHA-256 dataset fingerprints and UUID-based private storage paths.
- Supabase-backed projects, datasets, experiments, model runs, reports, and audit logs.
- Owner-scoped access, private Storage buckets, retention metadata, and audited deletion.

### Deterministic task decisions

- Binary classification, multiclass classification, and regression detection.
- Evidence for clustering, anomaly detection, and time-series forecasting.
- Target suitability scoring and ambiguity detection.
- Explicit `needs_clarification` outcomes instead of unsafe guessing.
- User-confirmed, versioned task overrides with audit history.
- Optional LLM suggestions are separated from deterministic decisions and cannot silently
  change the task.

### Data-quality and leakage protection

- Empty data, identifiers, constants, quasi-constants, duplicates, missingness, and high
  cardinality checks.
- Suspicious date fields, grouped entities, time ordering, target duplicates, near-perfect
  proxies, post-outcome names, and user-forbidden feature detection.
- Blocking errors versus non-blocking warnings.
- Explicit acknowledgement IDs for forced risky-feature overrides.
- Preprocessing fitted inside training folds to prevent validation leakage.

### Model tournaments

- Leakage-safe mixed numeric and categorical preprocessing.
- Resource-aware candidate planning.
- Classification and regression baselines plus optional XGBoost, LightGBM, and CatBoost.
- Cross-validation, full fold evidence, confidence intervals, out-of-fold predictions,
  calibration, and threshold evidence where applicable.
- Candidate failures are isolated and recorded instead of crashing the entire tournament.
- The winner is fitted only after model selection and stored with `skops` where supported.

### Unsupervised learning

- Clustering suitability checks and mixed-feature preprocessing.
- K-Means/MiniBatch, DBSCAN when suitable, and Gaussian-mixture comparisons.
- Cluster-number comparison, internal validity, and resampling stability.
- Robust statistical, Isolation Forest, LOF, and consensus anomaly evidence.
- Cautious segment descriptions that do not treat discovered groups as ground truth.

### Forecasting

- Explicit target, time column, frequency, horizon, and seasonal-period contracts.
- Timestamp sorting, duplicate/gap detection, and future-to-past leakage prevention.
- Rolling-origin validation.
- Naive, seasonal-naive, Holt-Winters, and bounded ARIMA-family candidates.
- Prediction intervals where the selected candidate supports them.

### Tuning and explanations

- Deterministic Optuna tuning with trial and time ceilings.
- Per-experiment and user-facing compute limits.
- Pruning evidence and dataset-size-based candidate reduction.
- Untuned baselines retained for honest comparison.
- Model-compatible global and local explanations.
- Bounded SHAP sampling, confusion/ROC/PR/calibration/residual evidence, and learning
  curves as applicable.
- Segment error analysis that does not claim correlation is causation.
- Private structured evidence artifacts stored before any narrative layer.

### Asynchronous and resumable execution

- FastAPI submits only experiment, owner, and job identifiers to Redis/Dramatiq.
- Idempotent job creation, database claims, progress, retries, cancellation, graceful
  shutdown handling, and stale-job recovery.
- Typed LangGraph workflow:

  ```text
  profile -> decide -> [clarify] -> plan -> [clarify] -> train -> finalize
  ```

- Owner-scoped Supabase checkpoints and pending writes.
- Clarification interrupts resume the same experiment, job, and graph thread.
- A completed checkpoint is returned without running training again.

### Grounded Hermes agent boundary

- Nous Hermes is the outer agent runtime; deterministic Python remains authoritative.
- A native tracked plugin exposes only explicitly allow-listed tools through FastAPI.
- HMAC-signed requests bind method, path, timestamp, nonce, trusted principal, and body.
- Owner identity and service credentials never appear in model-controlled arguments.
- Constitution approval, job start, clarification, and cancellation are explicit.
- Dataset-derived metadata is untrusted and raw rows are not returned to Hermes.
- Hash-addressed evidence prevents the language layer from changing recorded metrics.
- OpenRouter model selection is replaceable and configured privately through Hermes.

### Secure Hermes Telegram channel

- Official Telegram Bot API and Hermes Agent's bundled Telegram gateway are the primary route.
- Local development uses Hermes polling; no public webhook or deployment is configured.
- Only one configured numerical Telegram user ID is accepted, and private DMs are required.
- Trusted sender metadata is signed outside LLM-controlled arguments and verified by FastAPI.
- Seventeen strict ZubePredict tools cover projects, linking, upload/state, constitutions, jobs,
  evidence and temporary reports; no terminal or general Hermes tools reach Telegram.
- Authoritative Supabase state survives Hermes restarts without restarting experiments.
- CSV, XLSX and Parquet attachments are validated, fingerprinted, privately stored under
  UUID names, deduplicated, and removed from the gateway cache.
- The aiogram starter is a documented disabled fallback and cannot start without an
  explicit unsafe operational override.

### Unified authenticated dashboard

- Supabase email/password Auth with server-refreshed cookies and protected dashboard routes.
- Responsive project, private dataset upload, Auto/Expert Constitution, progress, leaderboard,
  plain-language verified evidence, styled Evidence Card and temporary report views.
- One-time eight-digit Telegram linking codes are HMAC-hashed, short-lived, single-use,
  rate-limited, auditable without raw codes, and revocable.
- Web and linked Telegram calls map to the same Supabase owner. Creation channel is descriptive
  metadata and never changes ownership.
- Browser source is automatically scanned for prohibited backend secret names.

## Architecture

```text
Browser / API client            Telegram Bot API → Hermes + OpenRouter
        |                                      |
        v                                      | signed trusted-channel tools
Next.js :3040 -----> FastAPI :8040 <-----------+
                              |
                              +---------------> Supabase Auth/Postgres/Storage
                              |
                              v
                         Redis :6379
                              |
                              v
                       Dramatiq worker
                              |
                              v
                 deterministic ML + LangGraph
                              |
                              v
                 artifacts, runs, checkpoints
```

Docker Compose manages Redis, the API, and the worker. The authenticated Next.js dashboard
runs separately from `apps/web` on port 3040 and calls the same FastAPI/LangGraph services as
Telegram.

## Technology stack

| Area | Technology |
|---|---|
| Backend API | Python 3.11, FastAPI, Uvicorn, Pydantic |
| Data and ML | pandas, NumPy, SciPy, scikit-learn, statsmodels |
| Advanced ML | XGBoost, LightGBM, CatBoost, Optuna, SHAP, skops |
| Orchestration | LangGraph |
| Agent layer | Nous Hermes v0.20.0 native plugin and OpenRouter |
| Jobs | Redis and Dramatiq |
| Persistence | Supabase Postgres, Auth, Storage, and RLS |
| Frontend | Next.js 15, React 19, TypeScript |
| Telegram | Official Bot API + Hermes Agent gateway; aiogram disabled fallback |
| LLM foundation | Template, OpenRouter, or Ollama-compatible client |
| Tooling | uv, pytest, Ruff, mypy, Docker Compose |

Python is deliberately constrained to `>=3.11,<3.13`. This workstation and the project
`.venv` use Python 3.11; Python 3.13 must not be used for this repository.

## Repository layout

```text
apps/
  api/                 FastAPI application and HTTP routes
  worker/              Dramatiq broker and experiment actors
  web/                 Next.js frontend on port 3040
  telegram_bot/        Explicitly disabled aiogram fallback only
packages/zubepredict_core/
  data_engine/         Loading, profiling, task detection, quality and leakage
  datasets/            Safe file handling and Supabase Storage lifecycle
  decisions/           Confirmed task overrides and audit history
  llm/                 Grounded provider abstraction
  ml_engine/           Preprocessing, tournaments, forecasting, tuning, explanations
  repositories/        Persistence contracts, records, and Supabase adapters
  shared/              Settings and typed schemas
  workflows/           LangGraph state machine and Supabase checkpointer
infrastructure/
  docker/              Python 3.11 image
  render/              Restricted demonstration API definition
  supabase/            Base schema and ordered migrations
integrations/
  hermes/              Native signed-tool plugin, configs, install and verification
scripts/               Diagnosis, tests, migration validation, and live smoke checks
tests/                 Unit and integration coverage
docs/                  Stage-specific details and roadmap
sample_data/           Demonstration dataset
```

## Prerequisites

On Windows, install:

- Python 3.11.x.
- Node.js and npm.
- Docker Desktop with Docker Compose.
- Git when version control is required.
- A Supabase project for persistent/authenticated workflows.

Recommended resources are at least 16 GB system RAM, 6 GB available to Docker, and 10 GB
free disk space for ML images and dependencies.

Run the non-secret diagnostic first:

```powershell
.\scripts\diagnose.ps1
```

## Environment setup

Create the private environment file once:

```powershell
Copy-Item .env.example .env
```

Never commit `.env` or paste its values into documentation, issues, prompts, or logs.

### Environment variables

| Variable | Purpose | Required now? |
|---|---|---|
| `SUPABASE_URL` | Hosted Supabase project URL | Yes for persistent workflows |
| `SUPABASE_ANON_KEY` | Browser/authenticated public API key | Yes for Auth/API flows |
| `SUPABASE_SERVICE_ROLE_KEY` | Trusted API/worker access | Yes server-side only |
| `REDIS_URL` | Dramatiq broker | Yes for async jobs |
| `LLM_PROVIDER` | `template`, `openrouter`, or `ollama` | Defaults to `template` |
| `OPENROUTER_API_KEY` | OpenRouter authentication | Only when selected |
| `HERMES_SERVICE_KEYS` | Rotatable `key-id:secret` API credentials | Stage 13 backend |
| `HERMES_DEV_PRINCIPAL_ID` | Explicit local Supabase owner UUID | Stage 13 development |
| `HERMES_TELEGRAM_OWNER_ID` | Numerical owner ID verified by FastAPI | Stage 14 backend |
| `HERMES_TELEGRAM_REPORT_TTL_SECONDS` | Temporary report URL lifetime | Stage 14 backend |
| `TELEGRAM_LINKING_CODE_SECRET` | Server-only one-time link-code HMAC key | Stage 15 linking |
| `TELEGRAM_SESSION_TTL_SECONDS` | Clears stale Telegram selections only | Stage 17 |
| `USER_API_REQUESTS_PER_MINUTE` | Per-owner API/Hermes rate cap | Stage 17 |
| `USER_UPLOADS_PER_DAY` | Per-owner completed upload cap | Stage 17 |
| `USER_STORAGE_QUOTA_MB` | Private active dataset byte cap | Stage 17 |
| `USER_EXPERIMENTS_PER_DAY` | Per-owner experiment-start cap | Stage 17 |
| `USER_CONCURRENT_EXPERIMENTS` | Active job cap; align database policy | Stage 17 |
| `DATASET_RETENTION_DAYS` | Age threshold for eligible private dataset cleanup | Stage 17 |
| `REPORT_RETENTION_DAYS` | Age threshold for eligible private report cleanup | Stage 17 |
| `REQUIRE_DATASET_PRIVACY_ATTESTATION` | Explicit upload privacy boundary | Production: `true` |
| `QUOTA_FAIL_CLOSED` | Reject mutations when distributed limits fail | Production: `true` |
| `OLLAMA_BASE_URL` | Local Ollama-compatible endpoint | Only when selected |
| `TELEGRAM_BOT_TOKEN` | Disabled aiogram fallback only in project `.env` | Leave blank with Hermes |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-visible API URL | Frontend integration |
| `NEXT_PUBLIC_SUPABASE_URL` | Browser-visible Supabase URL | Stage 15 dashboard Auth |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Browser-safe anon key | Stage 15 dashboard Auth |

Only variables beginning with `NEXT_PUBLIC_` are intended for the browser. Never create a
`NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY` or otherwise expose the service-role key.

The backend reads the root `.env`. Next.js reads `apps/web/.env.local`; copy only the three
documented `NEXT_PUBLIC_` values into that ignored frontend file. See
`docs/16-STAGE-15-DASHBOARD.md` for the complete Auth and linking setup.

The remaining limits and defaults are documented in `.env.example` and validated by
`packages/zubepredict_core/shared/config.py`.

Hermes has a separate ignored environment at `%LOCALAPPDATA%\hermes\.env`. Its variable
names are documented in `integrations/hermes/config/hermes.env.example`. The OpenRouter
key and Hermes service key must never enter Git, prompts, tool arguments, or frontend
variables.

## Create or repair the Python 3.11 virtual environment

Check the current interpreter:

```powershell
.\.venv\Scripts\python.exe --version
```

It must print Python 3.11.x. If `.venv` is missing or uses another version, remove it only
after confirming it is the project-local environment, then recreate it with the installed
Python 3.11 interpreter:

```powershell
$python311 = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
& $python311 -m venv .venv
.\.venv\Scripts\python.exe -m pip install uv
.\.venv\Scripts\uv.exe sync --extra dev --extra ml
```

## Supabase setup and migrations

The CLI work directory is `infrastructure/supabase`. Always include it when running
Supabase commands from the repository root.

For a completely new Supabase project, first open the Supabase SQL Editor and run the
complete contents of `infrastructure/supabase/001_initial_schema.sql` exactly once. It
creates the base tables, RLS policies, grants, trigger, and private Storage buckets. Do not
rerun it after it succeeds; subsequent changes belong in numbered migrations.

After the base schema exists, authenticate and apply the numbered migrations:

```powershell
npx supabase login
npx supabase link --project-ref YOUR_PROJECT_REF --workdir infrastructure/supabase
npx supabase db push --dry-run --workdir infrastructure/supabase
npx supabase db push --workdir infrastructure/supabase
```

Never put the project database password or access token into this README. Obtain the
project reference and database password from your own Supabase dashboard.

The ordered migrations are:

1. `20260809003207_secure_dataset_lifecycle.sql`
2. `20260809013027_intent_target_task_decisions.sql`
3. `20260809025738_async_experiment_jobs.sql`
4. `20260809045626_langgraph_workflow_checkpoints.sql`
5. `20260812132803_stage14_telegram_channel_state.sql`
6. `20260814124755_stage15_unified_dashboard_linking.sql`
7. `20260814165227_stage16_versioned_report_artifacts.sql`
8. `20260815002438_stage17_security_quotas_retention.sql`

The hosted development project is aligned through migration 8. On 2026-08-16, the owner confirmed
matching local/remote migration history, an empty `db push --dry-run`, all three Stage 17 schema
checks, and both quota triggers. This verifies the physical hosted schema as well as migration history.

If an older migration was previously executed manually in the SQL editor but is missing
from CLI history, do not replay it blindly. Confirm the schema exists, then use
`supabase migration repair <version> --status applied --linked` for only the confirmed
version. See `IMPLEMENTATION.md` for the historical correction made in this project.

Checkpoint tables are deliberately server-only. RLS is enabled, `anon` and
`authenticated` have no grants, and the service role is explicitly granted access.

Validate all migration SQL locally with a disposable PostgreSQL container:

```powershell
.\scripts\validate-supabase-migration.ps1
```

## Run with Docker

Docker Compose starts Redis, FastAPI, and the Dramatiq worker:

```powershell
docker compose up --build
```

Useful addresses:

- API health: <http://localhost:8040/health>
- Interactive API documentation: <http://localhost:8040/docs>
- Redis: `localhost:6379`

The frontend is not a Compose service. Start it in a second terminal:

```powershell
cd apps\web
npm install
npm run dev
```

Open <http://localhost:3040>.

Stop the Compose services with:

```powershell
docker compose down
```

Stop the frontend with `Ctrl+C` in its terminal.

## Run services manually

Use separate PowerShell terminals from the repository root.

### Terminal 1: Redis

```powershell
docker compose up redis
```

### Terminal 2: API

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\python.exe -m uvicorn zubepredict_api.main:app --host 0.0.0.0 --port 8040 --reload
```

### Terminal 3: worker

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\python.exe -m dramatiq apps.worker.tasks --processes 1 --threads 1
```

### Terminal 4: frontend

```powershell
cd apps\web
npm run dev
```

### Optional Terminal 5: Hermes CLI (Stage 13)

After completing the private setup in `integrations/hermes/README.md`:

```powershell
.\integrations\hermes\install-plugin.ps1
hermes plugins list
hermes
```

Hermes is not a Compose service. For the Stage 14 owner-only Telegram gateway, follow
`docs/15-STAGE-14-TELEGRAM.md`, then run the guarded polling wrapper:

```powershell
.\integrations\hermes\configure-telegram.ps1
.\scripts\smoke-stage14-telegram.ps1
.\integrations\hermes\start-telegram-gateway.ps1
```

Never paste the BotFather token into chat. It belongs only in `%LOCALAPPDATA%\hermes\.env`.

## API overview

All application routes except `/health` use the `/api/v1` prefix.

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Service health |
| `POST` | `/api/v1/analysis/profile` | Profile an uploaded file directly |
| `POST` | `/api/v1/analysis/detect-task` | Detect the ML task |
| `POST` | `/api/v1/analysis/quality` | Run quality/leakage checks |
| `POST` | `/api/v1/analysis/quick-tournament` | Run the bounded synchronous tournament |
| `POST` | `/api/v1/datasets/upload-intents` | Create an authenticated upload intent |
| `POST` | `/api/v1/datasets/finalize` | Validate and register a stored dataset |
| `DELETE` | `/api/v1/datasets/{dataset_id}` | Audited owned deletion |
| `POST` | `/api/v1/decisions/experiments/{id}/override` | Confirm a task override |
| `GET` | `/api/v1/decisions/experiments/{id}/history` | Read owned decision history |
| `POST` | `/api/v1/experiments/jobs` | Queue an idempotent experiment |
| `GET` | `/api/v1/experiments/{id}` | Read job status/result summary |
| `POST` | `/api/v1/experiments/{id}/resume` | Resume clarification on the same thread |
| `POST` | `/api/v1/experiments/{id}/cancel` | Request cancellation |

Authenticated routes require a Supabase user access token as a Bearer token. Job creation
also requires an `Idempotency-Key` header of at least eight characters.

The dedicated `/api/v1/hermes/*` surface contains thirteen signed tool endpoints. It is
service-authenticated and owner-scoped, not a replacement for browser Bearer Auth. See
`integrations/hermes/README.md` and `docs/architecture/ADR-013-hermes-agent-boundary.md`.

## Workflow states and resumability

An asynchronous experiment normally moves through:

```text
queued -> profiling -> training -> evaluating -> completed
```

It may instead enter `needs_clarification`, `cancelled`, or `failed`. A clarification
response is accepted only for `needs_clarification`. Task overrides require explicit user
confirmation and valid targets. Resumption requeues the same job ID and uses the same
experiment ID as the LangGraph thread ID.

## Testing and verification

Run the standard checks:

```powershell
.\scripts\test.ps1
```

Run the complete explicit gate:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe packages apps
.\.venv\Scripts\pytest.exe -q
cd apps\web
npm run build
```

Run the Stage 17 repository/security and migration gates from the repository root:

```powershell
.\scripts\security-scan.ps1
.\scripts\validate-supabase-migration.ps1
```

The last complete local Stage 17 verification recorded **233 passing pytest tests**, passing Ruff,
passing mypy across 69 source files, a passing Next.js 15.5.23 production build, a passing disposable
Stage 2–17 PostgreSQL chain, zero npm/Python advisory findings, and a passing workspace secret/state
scan. Trivy was unavailable, so `security-scan.ps1 -RequireTrivy` and a fresh non-root Docker image
build remain mandatory deployment gates rather than claimed passes.

Run the focused, no-paid-LLM Stage 13 gate:

```powershell
.\integrations\hermes\verify-stage13.ps1
```

Run the Stage 14 mocked integration tests without Telegram or provider spending:

```powershell
.\.venv\Scripts\pytest.exe tests\unit\test_stage14_*.py -q
```

Build Docker images without starting services:

```powershell
docker compose build api worker
```

Live Supabase smoke scripts create temporary users/records and clean them up. Run them only
against the intended development project:

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\python.exe scripts\smoke_supabase_stage2.py
.\.venv\Scripts\python.exe scripts\smoke_supabase_stage3.py
.\.venv\Scripts\python.exe scripts\smoke_supabase_stage4.py
.\.venv\Scripts\python.exe scripts\smoke_supabase_stage7.py
```

## Common troubleshooting

### Port 8040 or 3040 is already in use

```powershell
netstat -ano | Select-String ':8040|:3040'
```

Stop only the process you identify and own. Do not terminate unrelated services.

### `.venv` reports Python 3.13

Recreate the environment explicitly with the Python 3.11 executable as shown above. Merely
changing `pyproject.toml` does not replace an existing virtual environment interpreter.

### `Cannot find project ref`

The folder is not linked or the Supabase work directory was omitted:

```powershell
npx supabase link --project-ref YOUR_PROJECT_REF --workdir infrastructure/supabase
```

### Dry-run lists migrations already applied manually

Select No. Verify the corresponding remote schema, then repair only those confirmed
migration versions. Do not mark a migration applied if its schema is absent.

### React hydration attributes such as `data-gr-ext-installed`

Browser grammar/password extensions can inject attributes before React hydrates. The root
layout uses `suppressHydrationWarning` on `<body>` for this known extension-only mismatch.
Application-generated hydration mismatches still require an actual code fix.

### Docker build succeeds but `docker compose build web` fails

There is no `web` service in `compose.yaml`. Build the frontend with `npm run build` inside
`apps/web`; Compose currently contains only `redis`, `api`, and `worker`.

## Security model

- All persistent records carry an owner ID.
- Authenticated repositories use the user session and RLS.
- Service-role repositories exist only in the trusted API/worker.
- Queue messages contain identifiers, never files, access tokens, or Windows paths.
- Dataset objects and artifacts use private buckets and owner-prefixed UUID paths.
- Unsafe pickle loading is avoided; supported winner pipelines use `skops`.
- Graph checkpoints are private server-only implementation state.
- LLM text is an explanation layer and cannot create or modify verified metrics.
- Dataset cell content must be treated as untrusted data, never as an instruction.
- Hermes schemas forbid unknown fields and do not accept owner IDs, service keys, local
  paths, SQL, or arbitrary URLs.
- The local Hermes principal mapper is refused in production; production requires an
  independently authenticated mapping and shared replay store.
- Telegram's effective Hermes runtime toolset is exactly `zubepredict`; terminal, filesystem,
  browser, code execution, cron, delegation, Kanban and globally configured MCP tools are
  excluded. Broad/global gateway allowlists, allow-all flags, groups and non-owner pairing
  approvals fail startup.
- Telegram tokens remain only in the ignored Hermes environment and never enter Next.js,
  Supabase, API responses, logs or screenshots.
- Report artifacts are generated once from Evidence Envelope v2, privately stored with version,
  byte-size, SHA-256 and evidence-hash metadata, then shared unchanged across web, Telegram and
  authenticated API access.
- Human-facing report version 4 provides a styled HTML/PDF Evidence Report, a concise HTML EyeCare
  Evidence Card, a plain-language HTML Model Card, a readable HTML Reproducibility Manifest and a
  formatted prediction workbook. The authenticated dashboard serves verified HTML bytes through
  FastAPI because Supabase Storage intentionally returns HTML as plain text. Guided explanations
  lead the reader while technical sections remain expandable; old report versions stay immutable.
- Report links are owned, audited, generic, and expire after a bounded short interval.
- Stage 17 enforces per-owner API/upload/experiment counters through Redis, private retained-byte
  limits, database-serialized concurrent experiment limits, production fail-closed behavior and
  bounded Telegram session state.
- Customer uploads carry an explicit authorisation/de-identification attestation when the
  production privacy gate is enabled. This attestation never substitutes for governance review.
- Dataset and report retention metadata is enforced through a dry-run-first, audited private
  deletion workflow. Legal-hold records are excluded from automated deletion.
- Common secrets are redacted from structured logs, Hermes/conversation state is excluded from
  Git and Docker contexts, and a local security scan checks secret boundaries and dependencies.

## Known limitations and roadmap

Completed in code and automated verification: Stages 0 through 17. The Stage 17 migration is applied
and verified on the hosted development database. The production-only checklist remains incomplete,
and no public infrastructure deployment has been performed.

Not yet completed:

- Stage 18: demonstration deployment and operational monitoring.

Production identity scaling beyond the current private owner gateway, shared replay protection,
patched-Hermes compatibility validation and operational monitoring remain later work. The pinned
Hermes v0.20.0 must not be publicly deployed until a patched revision is revalidated and pinned.
Render configuration is a restricted demo starting point. No public deployment was performed.

## Additional documentation

- `docs/01-BEGINNER-SETUP-WINDOWS.md`
- `docs/02-ACCOUNTS-AND-KEYS.md`
- `docs/03-BUILD-ROADMAP.md`
- `docs/04-STAGE-2-SUPABASE.md` through `docs/13-STAGE-12-LANGGRAPH-ORCHESTRATION.md`
- `docs/architecture/ADR-013-hermes-agent-boundary.md`
- `docs/architecture/ADR-014-hermes-telegram-trusted-channel.md`
- `docs/15-STAGE-14-TELEGRAM.md`
- `docs/16-STAGE-15-DASHBOARD.md`
- `docs/17-STAGE-16-REPORTING.md`
- `docs/18-STAGE-17-SECURITY.md`
- `integrations/hermes/README.md`
- `docs/codex-prompts/00-MASTER-PROMPT.md`
- `IMPLEMENTATION.md`

## Licence note

This original scaffold is maintained for the ZubePredict AI project. Every third-party
library, model, hosted service, and generated artifact retains its own licence and terms;
review them before commercial distribution.

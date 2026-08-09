# ZubePredict AI

ZubePredict AI is an evidence-driven, stage-built data-science platform. It accepts
tabular datasets, validates and profiles them, determines an appropriate machine-learning
task, blocks unsafe leakage patterns, compares suitable models, persists reproducible
evidence, and pauses for human clarification when a decision cannot be made safely.

The repository currently implements Stages 0 through 12 of the project roadmap. The
next planned stage is Stage 13, the grounded Nous Hermes language layer. The existing
language-provider abstraction is only a foundation; it is not yet the completed Stage 13
integration.

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

## Architecture

```text
Browser / API client
        |
        v
Next.js :3040 -----> FastAPI :8040 -----> Supabase Auth/Postgres/Storage
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

The frontend is currently a starter landing interface. The complete authenticated project
dashboard is planned for Stage 15. Docker Compose currently manages Redis, the API, and
the worker; the Next.js frontend runs separately from `apps/web`.

## Technology stack

| Area | Technology |
|---|---|
| Backend API | Python 3.11, FastAPI, Uvicorn, Pydantic |
| Data and ML | pandas, NumPy, SciPy, scikit-learn, statsmodels |
| Advanced ML | XGBoost, LightGBM, CatBoost, Optuna, SHAP, skops |
| Orchestration | LangGraph |
| Jobs | Redis and Dramatiq |
| Persistence | Supabase Postgres, Auth, Storage, and RLS |
| Frontend | Next.js 15, React 19, TypeScript |
| Bot foundation | aiogram |
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
  telegram_bot/        Early polling bot foundation
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
| `OLLAMA_BASE_URL` | Local Ollama-compatible endpoint | Only when selected |
| `TELEGRAM_BOT_TOKEN` | Telegram bot authentication | Future Telegram work |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-visible API URL | Frontend integration |
| `NEXT_PUBLIC_SUPABASE_URL` | Browser-visible Supabase URL | Future dashboard Auth |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Browser-safe anon key | Future dashboard Auth |

Only variables beginning with `NEXT_PUBLIC_` are intended for the browser. Never create a
`NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY` or otherwise expose the service-role key.

The remaining limits and defaults are documented in `.env.example` and validated by
`packages/zubepredict_core/shared/config.py`.

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

## Known limitations and roadmap

Completed: Stages 0 through 12.

Not yet completed:

- Stage 13: hardened Nous Hermes/OpenRouter/Ollama structured language layer.
- Stage 14: secure Telegram experiment workflow.
- Stage 15: full authenticated Next.js dashboard.
- Stage 16: HTML/PDF/model-card reporting.
- Stage 17: production quotas, retention automation, and security hardening.
- Stage 18: demonstration deployment and operational monitoring.

The Telegram app and LLM client currently present in the repository are foundations, not
claims that those later stages are finished. Render configuration is a restricted demo
starting point, not a production deployment.

## Additional documentation

- `docs/01-BEGINNER-SETUP-WINDOWS.md`
- `docs/02-ACCOUNTS-AND-KEYS.md`
- `docs/03-BUILD-ROADMAP.md`
- `docs/04-STAGE-2-SUPABASE.md` through `docs/13-STAGE-12-LANGGRAPH-ORCHESTRATION.md`
- `docs/codex-prompts/00-MASTER-PROMPT.md`
- `IMPLEMENTATION.md`

## Licence note

This original scaffold is maintained for the ZubePredict AI project. Every third-party
library, model, hosted service, and generated artifact retains its own licence and terms;
review them before commercial distribution.

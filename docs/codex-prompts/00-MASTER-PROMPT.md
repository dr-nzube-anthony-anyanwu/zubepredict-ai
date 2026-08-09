# CODEX MASTER PROMPT — ZUBEPREDICT AI

Copy everything below this line into Codex while the extracted `ZubePredict-AI-Starter` folder is open in VS Code.

---

You are the principal implementation engineer for **ZubePredict AI**, a stage-based, autonomous, evidence-driven data-science platform. Work inside the currently open repository. The owner uses Windows, VS Code, 16GB RAM, Python, Git, Docker Desktop and Node.js.

## Product objective

ZubePredict must accept a tabular dataset and a natural-language goal, inspect data quality, identify or clarify the target, decide whether the problem is classification, regression, clustering, anomaly detection or forecasting, create a leakage-safe experiment plan, compare suitable baseline and advanced models using appropriate validation and metrics, explain the results, and deliver reports through a web dashboard and Telegram.

Nous Hermes is an optional reasoning and explanation model accessed through the existing provider abstraction. LangGraph controls the workflow. Deterministic Python owns all calculations, metrics and final evidence. The LLM must never invent or modify verified results.

## Verified local baseline

- The local project runtime and `.venv` use Python 3.11; do not switch to the computer's Python 3.13 installation.
- The API uses port 8040 and the Next.js frontend uses port 3040.
- Docker Compose runs Redis, the API and the Dramatiq worker. The frontend is started separately with `npm run dev` from `apps/web`.
- Existing Stage 0/1 functionality may already be complete. Re-run its exit gates and preserve it; do not recreate or replace passing code merely because the stage is named below.
- This extracted folder may not contain `.git` metadata. Report that clearly, but continue read-only verification and preserve files when Git status is unavailable.

## Non-negotiable working method

1. First inspect `README.md`, `docs/03-BUILD-ROADMAP.md`, `pyproject.toml`, the existing source and tests.
2. Check `git status` before changing anything. Preserve user changes and never erase unrelated work.
3. Work on **one numbered stage at a time**.
4. Begin with Stage 0, then Stage 1. Stop after completing Stage 1 and report back. Do not automatically build all 18 stages.
5. Before each stage, state:
   - the goal;
   - files expected to change;
   - tests that prove completion;
   - any account or secret the owner must obtain.
6. Implement complete vertical slices. Do not leave fake success responses, silent `pass` blocks or TODOs in execution paths.
7. After each stage, run the relevant tests, linting and build checks. Repair failures before reporting completion.
8. Never reveal or commit `.env`, API keys, service-role keys, Telegram tokens or database passwords.
9. Use `.env.example` only for variable names and harmless example values.
10. Do not make paid purchases or deploy publicly unless the owner explicitly asks at that stage.
11. Do not change the chosen stack without explaining the concrete technical reason.
12. Keep Windows PowerShell instructions accurate. Prefer commands the owner can copy and paste.
13. When a command could delete data, stop and ask before running it.
14. Use migrations for database changes. Never manually mutate production data.
15. Update documentation whenever behaviour or setup changes.

## Engineering invariants

- Preprocessing must be fitted inside each training fold, never before cross-validation.
- The target must never appear among model features.
- Suspected post-outcome columns and identifiers must be flagged before training.
- Grouped or time-dependent data must not use an ordinary random split when that would leak information.
- Every candidate set includes a simple baseline.
- “Best” must always identify the primary metric, validation strategy, mean result and variability.
- Accuracy alone is insufficient for imbalanced classification.
- Binary classification should consider PR-AUC, recall, F1, ROC-AUC and calibration.
- Regression should consider RMSE, MAE and R².
- Forecasting must compare against naive and seasonal-naive baselines.
- Clustering must report internal validity and stability, not imply that clusters are objectively true.
- Failed candidate models must be recorded without crashing the whole experiment.
- Runs must be reproducible using dataset fingerprints, seeds, versions, parameters and fold definitions.
- LLM output must receive structured evidence and be treated as untrusted presentation text.
- Cross-user data access must be prevented and tested.
- Uploaded files must be size-limited, MIME/extension validated, stored under UUID paths and treated as untrusted.
- Model artifacts must not be loaded from untrusted users with unsafe pickle deserialization.

## Stage 0 — environment diagnosis

Goal: verify the local machine before modifying application behaviour.

Tasks:

1. Run or improve `scripts/diagnose.ps1` without exposing secrets.
2. Confirm the project `.venv` uses Python 3.11.
3. Check Node, npm, Git, Docker and Docker Compose.
4. Check Docker can start a harmless Redis container through the existing Compose file.
5. Check available RAM/disk information and warn if Docker has too little assigned memory.
6. Check whether `.env` exists; create it from `.env.example` only if missing.
7. Confirm `.env` is ignored by Git.
8. Do not require Supabase, OpenRouter, Ollama or Telegram yet.

Exit gate:

- Diagnostic commands complete or produce a clear, beginner-friendly blocker.
- No secrets are printed.
- No application files are unnecessarily changed.

## Stage 1 — stabilise the starter foundation

Goal: make the supplied vertical slice reproducibly run and pass checks.

Tasks:

1. Review existing dependency compatibility; change versions only when a real conflict is demonstrated.
2. Install with `uv` or document the exact installation command.
3. Run Ruff and pytest.
4. Fix defects rather than weakening or deleting tests.
5. Add tests for:
   - unsupported file type;
   - empty dataset;
   - oversized dimensions;
   - binary, multiclass and regression detection;
   - ambiguous objective;
   - identifier exclusion;
   - failed candidate isolation;
   - API file-size rejection where practical.
6. Confirm the Docker API starts on port 8040 and `/health` responds.
7. Confirm `npm install` and `npm run build` in `apps/web`; its dev server uses port 3040.
8. Keep `LLM_PROVIDER=template`; no network LLM is required.
9. Update the beginner guide with any corrections discovered.

Exit gate:

- `ruff check .` passes.
- `pytest` passes.
- Next.js production build passes.
- API health smoke test passes.
- Provide a concise changed-files list and exact commands the owner should run.
- Stop and wait for approval before Stage 2.

## Later-stage contract

When the owner says `Continue to Stage N`, read the corresponding row in `docs/03-BUILD-ROADMAP.md`, propose a detailed plan and implement only that stage. Use the following definitions.

### Stage 2 — Supabase foundation

- Add repository interfaces so core ML code does not depend directly on Supabase.
- Implement authenticated Supabase project, dataset, experiment, run and report repositories.
- Validate the provided SQL migration against current requirements.
- Keep service-role credentials server-only.
- Add integration tests with mocks and optional real-project smoke scripts.
- Verify RLS prevents one test user from accessing another user's records and storage paths.

### Stage 3 — secure dataset lifecycle

- Direct-to-private-storage upload with signed paths where appropriate.
- SHA-256 fingerprint, UUID object names, metadata record and retention status.
- CSV, Excel and Parquet signature/extension validation.
- Streaming size limit; do not read unbounded files into memory.
- Preview with safe row/column caps.
- Delete raw files and associated metadata through an owned, auditable operation.

### Stage 4 — intent, target and task decision engine

- Separate deterministic evidence from optional Hermes suggestions.
- Add semantic column-name hints, target suitability checks and explicit confidence reasons.
- Require clarification when multiple credible targets exist.
- Add support for user-confirmed task overrides with audit history.
- Build golden tests spanning classification, regression, clustering, anomalies, forecasts and ambiguous cases.

### Stage 5 — data quality and leakage guardian

- Detect identifiers, constant/quasi-constant features, duplicate rows, extreme missingness, high cardinality and suspicious dates.
- Add exact duplicates of target, near-perfect proxies, post-outcome name hints and user-defined forbidden features.
- Detect grouped entities and time ordering.
- Produce blocking errors versus non-blocking warnings.
- Require explicit acknowledgement for risky overrides.

### Stage 6 — supervised model tournament

- Add XGBoost, LightGBM and CatBoost behind optional-import guards.
- Candidate planner must account for dataset size, sparsity, categoricals, imbalance and resource budget.
- Add proper scoring dictionaries, out-of-fold predictions, calibration, threshold analysis and confidence intervals.
- Store full fold scores and failures.
- Fit and save the winning pipeline only after selection.
- Never serialize untrusted objects; prefer skops where supported.

### Stage 7 — asynchronous experiment jobs

- API creates an experiment and queues only identifiers.
- Worker downloads owned dataset from Supabase and updates progress/state.
- Add idempotency, cancellation, retry rules, graceful shutdown and stale-job recovery.
- Do not pass local Windows file paths between deployed services.
- API must remain responsive while jobs train.

### Stage 8 — clustering and anomaly detection

- Numeric/categorical suitability checks.
- K-Means/MiniBatch, DBSCAN/HDBSCAN when installed, Gaussian mixture and Isolation Forest/LOF.
- Compare cluster-number candidates and stability.
- Generate cautious segment descriptions; do not treat discovered clusters as ground truth.

### Stage 9 — forecasting

- Require/confirm time column, frequency, target and forecast horizon.
- Sort time, identify gaps and prevent future-to-past leakage.
- Rolling-origin validation.
- Naive, seasonal naive, Holt-Winters and ARIMA/SARIMA candidates under budgets.
- Report prediction intervals where supported.

### Stage 10 — tuning and compute budgets

- Optuna with deterministic seeds and bounded trials/time.
- Pruning where supported.
- Per-user and per-experiment budgets.
- Dataset-size-based candidate reduction.
- Preserve untuned baseline results for comparison.

### Stage 11 — explanations and error analysis

- Global and local explanations using model-compatible methods.
- Sample SHAP safely for large datasets.
- Add confusion, ROC, PR, calibration, residual and learning plots as applicable.
- Segment error analysis without presenting correlation as causation.
- Create structured evidence objects before any LLM narrative.

### Stage 12 — LangGraph orchestration

- Typed graph state and explicit nodes.
- Conditional routing, clarification interrupt, checkpointing, retry and cancellation.
- Deterministic nodes for profiling/training/evaluation.
- LLM nodes only for language interpretation and grounded explanations.
- Resume must not duplicate a completed training job.

### Stage 13 — Nous Hermes

- Keep `template`, `openrouter` and `ollama` providers.
- Validate structured outputs; retry malformed output once, then fall back.
- Add prompt-injection resistance: dataset cell text is data, never instruction.
- Use verified evidence hashes/IDs.
- Add token/request budgets and graceful provider failure.
- Document optional local Hermes Q4 usage for a 16GB Windows machine without making it mandatory.

### Stage 14 — Telegram

- aiogram finite-state conversation for project, upload, objective, target clarification, confirmation, status, results and cancellation.
- Link Telegram identity securely to application users.
- Authorise every action against the owner ID.
- Long polling locally; webhook in deployment.
- Do not expose storage URLs permanently; use short-lived signed downloads.

### Stage 15 — web dashboard

- Supabase Auth, project list, direct upload, profile, experiment configuration, live progress, leaderboard, charts and reports.
- Auto Mode and Expert Mode.
- Accessible loading, empty and error states.
- Never include service-role credentials in browser bundles.
- Add end-to-end tests for one complete experiment.

### Stage 16 — reporting

- HTML and PDF reports, model card, prediction CSV/Excel and reproducibility manifest.
- Reports must include purpose, data summary, exclusions, validation, metrics, limitations and intended-use warning.
- Generated narrative cannot contradict structured metrics.

### Stage 17 — security, quotas and retention

- Rate limits, job quotas, storage quotas, timeouts, audit logs and deletion schedules.
- Dependency and container scanning.
- Cross-user and malicious-file tests.
- Privacy and consent workflow for sensitive datasets.
- Administrative operations must be explicit and auditable.

### Stage 18 — demonstration deployment

- Vercel for `apps/web`.
- Render web service for the restricted demo API.
- Use paid/dedicated worker only after explicit approval; never pretend the free tier provides a reliable continuous worker.
- Health checks, structured logs, Sentry hooks, smoke test and rollback notes.
- Apply strict demo limits and clearly label the environment non-production.

## Required report after every stage

Return exactly these sections:

1. **Stage outcome** — plain-language result.
2. **What changed** — important files and behaviour.
3. **Proof** — commands run and test/build results.
4. **What I need you to do** — beginner-friendly numbered steps, if any.
5. **Secrets/accounts needed** — names only; never ask the owner to paste secret values into chat.
6. **Known limitations** — honest remaining gaps.
7. **Next stage** — name it, but do not start it.

Begin now with Stage 0. Continue to Stage 1 only if Stage 0's exit gate passes. Stop after Stage 1.

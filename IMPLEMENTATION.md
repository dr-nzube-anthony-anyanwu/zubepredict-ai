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
4. Treat Stages 0 through 17 as an existing working baseline; do not rebuild them from
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

Last updated: 2026-08-16.

Current stopping point: **Stage 17 security/privacy/quota hardening is implemented and locally
verified. Its migration is applied and physically verified on the hosted development Supabase
project. No public deployment was performed. Do not begin Stage 18 without explicit approval.**

The product now includes the backend/ML/orchestration foundation, hardened local
Hermes/OpenRouter Telegram boundary, authenticated Next.js dashboard, secure one-time account
linking, one backend-generated versioned report bundle shared by every channel, distributed
per-owner quotas, privacy attestation, retention execution and a production security gate.
Multi-instance replay protection, patched-Hermes revalidation and deployment remain future work.

Current runtime state at the last verification:

- Stage 17 did not start FastAPI, Next.js, the worker or Hermes. The disposable PostgreSQL migration
  validator removes its container in cleanup; no Stage 17 service is intentionally left running.
- The local project `.venv` reports Python 3.11.0.
- Hermes Agent v0.20.0 (2026.8.3) is installed at pinned commit
  `3c27eb6234bf91b8ceee9e9071591b31e9b148cb` with managed Python 3.11.0.
- API and worker Docker images built successfully through Stage 16. The Stage 17 non-root rebuild
  was attempted twice but the Docker client hung past the verification timeout; both exact client
  processes were stopped and no containers were left running.
- The hosted Supabase database supports the live Stage 14 owner flow; no secret values or
  signed report URLs are recorded in this file.
- The Supabase project is linked locally under `infrastructure/supabase`.
- Supabase migration history is aligned remotely through Stage 17, including
  `20260815002438_stage17_security_quotas_retention.sql`.
- On 2026-08-16, the owner confirmed an up-to-date dry run, the Stage 17 server-only limits table,
  dataset privacy field, report retention field and both database quota triggers on the hosted
  development project. This confirms physical schema state rather than migration history alone.
- The tracked Hermes plugin manifest is v0.4.0. Because Stage 17 changed plugin/runtime policy files,
  refresh the installed plugin configuration before the next live Telegram verification; do not
  assume the managed Hermes copy already contains uncommitted workspace changes.

Latest complete regression evidence:

- 147 pytest tests passed after Stage 13.
- Stage 13 focused preflight verification passed 13 tests before Stage 14 edits.
- The first Stage 14 security/integration slice passed 40 tests. After the final exact report-link
  delivery and early trusted-principal corrections, the full regression passed 199 tests.
- The final Stage 15 regression passed **214 pytest tests**.
- The final Stage 16 report-version-4 delivery regression passed **225 pytest tests**; Ruff passed, mypy
  passed across 48 source files, Next.js 15.5.23 production build passed, and the disposable
  PostgreSQL migration chain passed with 14 RLS policies and seven report-integrity columns.
- The final Stage 17 regression passed **233 pytest tests**; Ruff passed; mypy passed across 69
  source files; the Next.js production build passed; and the disposable migration chain passed
  with 14 RLS policies, seven report-integrity columns, six privacy/retention columns, every public
  table RLS-enabled and both atomic quota triggers present.
- `npm audit` and the isolated Python `pip-audit` both reported **0 known vulnerabilities**. The
  workspace secret/state scan passed. Trivy was unavailable and remains mandatory before deployment.
- Official Hermes discovery loaded 13 native ZubePredict tools before Stage 14. After the
  Stage 14 reinstall, Hermes discovery verified the enabled v0.2.0 plugin with 16 tools,
  the workflow skill, pre-LLM hook and exact report-output transform hook. The focused
  Hermes verifier passed 15 tests after the correction.
- Stage 15 installed plugin v0.3.0 with 17 tools and verified exactly seven safe non-admin
  Telegram commands, including direct `/zlink` and `/zreport` paths.
- A disposable Docker API runtime reported Python 3.11.15 and imported the Stage 12
  workflow successfully.
- The full SQL migration chain through Stage 16 passed against disposable PostgreSQL with 14 RLS
  policies and seven report-integrity columns. The Stage 16 migration was also applied remotely.
- Read-only hosted Supabase checks confirmed the Stage 3, 4, 7, and 12 schema.
- Agent-browser visually verified the landing and login pages with no console/browser errors.

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
| Next.js | `apps/web` | Supabase-authenticated unified dashboard on port 3040 |
| Telegram | `integrations/hermes` | Official Hermes gateway and restricted signed plugin |
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
| `20260812132803` | Telegram account links, resumable state and one-time linking codes |
| `20260814124755` | Unified dashboard source metadata and Telegram linking attempts |
| `20260814165227` | Versioned channel-independent report artifacts and integrity metadata |
| `20260815002438` | Security limits, privacy attestations, retention metadata and quota triggers |

The hosted development project is aligned through `20260815002438`. The owner verified matching
local/remote history, no pending dry-run migration, the expected Stage 17 table/columns and both
quota triggers on 2026-08-16.

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

### Stage 13 — Nous Hermes grounded agent boundary

Completed a Stage 12.5 alignment audit, then installed Hermes Agent v0.20.0 (2026.8.3)
from immutable commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`. The pre-migration
Hermes configuration was backed up privately under the local Hermes home, and
`hermes doctor --fix` migrated its configuration schema from v0 to v33.

Added:

- A tracked native plugin under `integrations/hermes/plugin/zubepredict`, using the
  official `plugin.yaml` and `register(ctx)` convention.
- Exactly thirteen tools: health, project list/create, dataset profile, readiness,
  constitution create/confirm, experiment start/status, clarification answer,
  cancellation, evidence, and report metadata.
- A dedicated `/api/v1/hermes/*` FastAPI boundary. Hermes never connects directly to
  Supabase and never receives the service-role key.
- HMAC-SHA256 authentication with rotated key IDs, timestamp expiry, one-use nonces,
  trusted principal binding, full-path/body integrity, and constant-time comparison.
- Strict schemas that keep owner identity, credentials, local paths, SQL, and arbitrary
  URLs outside model-controlled arguments.
- Reuse of the existing owned experiment record for versioned proposed/approved
  constitutions and durable job execution. No Supabase migration was required.
- Explicit constitution approval, version checks, idempotent start, clarification checks,
  target/task validation, cancellation confirmation, and bounded stable errors.
- A frozen hash-addressed evidence envelope. Narratives containing unrecorded models or
  numbers fall back to a deterministic verified summary.
- An ephemeral pre-LLM injection guard, bundled workflow skill, installer, safe config
  examples, focused verifier, ADR, operator guide, and no-paid-LLM automated tests.

At the end of Stage 13, Telegram was not installed or configured.

### Stage 14 — Hermes Telegram gateway and secure channel integration

Implemented the official route `Telegram Bot API → pinned Hermes gateway → OpenRouter →
ZubePredict plugin → FastAPI → LangGraph/worker → Supabase`. No public webhook or deployment
was created; local development uses Hermes polling.

Added:

- Trusted Telegram identity from Hermes task-local `HERMES_SESSION_*` ContextVars, outside
  prompt text. Channel and numerical sender are covered by the Stage 13 HMAC signature.
- Two owner checks before business operations: Hermes/plugin numerical allowlist plus DM
  restriction, then FastAPI development mapping to the configured Supabase owner UUID.
- Production refusal, global/per-platform allow-all refusal, global allowlist refusal,
  hard group denial before LLM dispatch, pairing-approval preflight and privacy-safe denial
  logging. The pinned Telegram adapter uses an impossible group-chat allowlist entry (`0`)
  with guest mode disabled; the plugin independently rejects non-DM context.
- Three native tools: restricted attachment upload, authoritative channel state and safe
  channel reset. Telegram's effective platform toolset exposes exactly `zubepredict`; disabled
  STT and `no_mcp` are configuration-only resolution markers.
- Server-only Supabase tables for account links, resumable state and hashed one-time linking
  codes. RLS is enabled and `anon`/`authenticated` privileges are revoked.
- Secure CSV/XLSX/Parquet ingestion: cache-root containment, size limit, extension/MIME/
  signature validation, macro rejection, SHA-256, UUID private path, duplicate reuse, audit
  events and cleanup on every success/failure path.
- Authoritative state updates for selected project/dataset, readiness, Constitution version
  and approval, active experiment, clarification, progress, completion, cancellation/reset.
- Owner-checked audited evidence-report creation and five-minute signed access. No permanent
  public URL or local path is returned.
- A production-oriented one-time account-linking service that stores only HMAC hashes,
  expires and consumes codes once, and supports revocation. Stage 15 owns its public UI/API.
- Guarded configure/start/smoke scripts, beginner runbook, ADR-014, security/injection tests
  and a mocked end-to-end conversation.
- The previous aiogram starter now fails closed unless an explicit fallback override is set;
  it must never run with Hermes.

Correction found during the real pinned-runtime tool listing: saving only
`platform_toolsets.telegram: [zubepredict]` was insufficient. Hermes interpreted the value written
by `config set` as a string, then recovered its full Telegram defaults. The configurator now uses
Hermes's Python config API to save a real list, includes disabled STT to make it authoritative,
uses `no_mcp`, globally suppresses the recovered Kanban toolset, and fails unless resolution is
exactly `{stt, zubepredict}` with STT disabled. This prevents terminal, file, browser, code
execution, cron, delegation and unrelated MCP exposure.

Correction found during the real Telegram document smoke test: the original Windows attachment
example pointed to `C:\Users\<user>\.hermes\cache\documents`, but the managed pinned Hermes
installer actually caches Telegram documents under its LocalAppData Hermes home. Telegram had
successfully downloaded the CSV and Hermes correctly supplied both inlined text and a cached-file
marker; the plugin rejected the file because its configured containment root was wrong. The plugin
Windows default and environment example now use the managed cache, and both gateway startup and
the smoke preflight fail early when an explicitly configured root differs from that managed cache.

Correction found during the real temporary-report smoke test: Supabase generated a valid signed
Storage URL, but OpenRouter/Hermes abbreviated the 381-character JWT with a literal ellipsis while
writing its friendly Telegram reply. Supabase then correctly rejected the altered token as an
invalid compact JWS. A secret-safe live diagnostic proved the backend URL had three JWT segments
and downloaded successfully with HTTP 200. The plugin now binds a successful report reference to
the trusted Hermes session in bounded, expiring process memory and uses Hermes's supported
`transform_llm_output` hook to deliver that exact URL once to the matching Telegram session. The
LLM no longer transcribes the token. Tests cover verbatim delivery, one-time consumption and
cross-session isolation. No signed URL or token is logged or persisted by this mechanism.
The first live retest exposed a test/runtime mismatch: the unit test supplied platform
`telegram`, but pinned Hermes passes the string representation `Platform.TELEGRAM` to the
transform hook. The strict comparison therefore skipped the transformer and the model shortened
the second URL too. Platform normalization now accepts the pinned enum representation while still
matching only Telegram, and the regression test uses `Platform.TELEGRAM`. The complete 193-test
suite and Ruff passed again before reinstalling and restarting only the Hermes gateway.
The following live retest still produced an abbreviated token. A secret-safe structural read of
Hermes `state.db` found that the backend tool result contained a valid 381-character, three-part
JWT with no ellipsis, while the assistant reply contained a 13-character token with a literal
ellipsis; the deterministic marker was absent. No URL, token, message body or identifier was
printed. The plugin now captures successful report results through Hermes's official
`post_tool_call` lifecycle hook instead of depending only on tool-handler keyword context. It also
registers `/zreport`, which reads the authoritative active experiment, calls the same signed and
owner-checked FastAPI report route, and returns the exact five-minute URL through Hermes's direct
plugin-command path without invoking the LLM. The first command name `/report` was intercepted by
Hermes's non-admin slash-command policy before plugin dispatch and left a prolonged typing
indicator. The product command was renamed `/zreport` and added as the sole product-specific entry
to the exact non-admin Telegram command allowlist. A second live denial exposed that Hermes CLI
had serialized both list settings as strings: the string `"[]"` enabled gating as a fake admin ID,
and the comma-containing command string could not match `zreport`. The configurator now writes
real lists through Hermes's Python config API. It uses impossible Telegram ID `0` as the sole admin
sentinel because a genuinely empty admin list disables Hermes slash gating; therefore nobody gets
admin commands, while the owner can use only the six safe commands. Verification exercises the
actual pinned `policy_from_extra` logic and proves `/zreport` allowed and an admin command denied.
Broad/admin commands remain denied. Gateway
startup and smoke preflight now fail if this allowlist drifts. The reloaded runtime verified that
`/zreport`, the
post-tool hook and the output transformer are all registered. Ruff and all 195 tests passed.
The next live `/zreport` reached the plugin but returned "report reference unavailable." FastAPI
access logs showed `/hermes/channel/state` returning `409 not_telegram`. Inspection of pinned
Hermes v0.20.0 established that plugin slash commands run before Hermes binds its normal
`HERMES_SESSION_*` ContextVars. The plugin now captures the official gateway event's transport
metadata through `pre_gateway_dispatch`, then applies the same fail-closed numerical-owner and
private-DM checks before signing the backend request. This metadata is never taken from the LLM or
message text. A live secret-safe check recovered the authoritative active experiment and a complete
three-segment signed token with no ellipsis. Ruff and all 199 tests passed before reinstalling the
plugin and restarting only the Hermes gateway.

Manual smoke-test status:

- The repository never received or inspected the BotFather token or owner ID.
- The owner configured private values without sharing them with Codex. The live bot flow has
  successfully exercised project creation, safe CSV upload, experiment execution, status,
  evidence and report generation. The corrected `/zreport` link downloaded the complete evidence
  JSON successfully; inspection confirmed the evidence structure and found no token, signed URL,
  local path, stack trace or secret in the downloaded artifact.
- The owner confirmed a separately queued synthetic experiment became cancelled, resetting the
  Telegram selections did not delete that experiment, and a second unapproved Telegram account
  received no response. The authorised owner account continued working normally.
- All required Stage 14 manual owner smoke checks are complete. Stage 15 has not started.
- Proactive outbound notifications are deferred; the MVP queries authoritative status.

### Stage 15 — unified Next.js dashboard, Auth and Telegram account linking

Implemented one owner-scoped product surface rather than a Telegram-only data system:

- Replaced the starter page with a responsive authenticated Next.js 15/React 19 workspace and
  added Supabase SSR browser/server clients, cookie refresh middleware, email/password sign-in,
  signup, callback and sign-out flows.
- Added owned dashboard endpoints for overview, project creation, experiment detail,
  Constitution creation/confirmation, durable experiment start, immutable evidence and temporary
  report access. These reuse the Stage 14 service functions instead of creating a second ML path.
- The dashboard presents projects/datasets from both channels, experiment status, pending
  clarification, Constitution fields, model leaderboards, reports and safe audit metadata.
- Added private browser upload through the existing signed upload-intent/finalize boundary.
  Supabase Storage remains private and the backend performs validation and fingerprinting.
- Added Auto Mode and Expert Mode. Expert Mode can constrain candidate-model count and training
  timeout, while both modes retain task/leakage/evidence guardrails and explicit Constitution
  confirmation.
- Added authenticated one-time Telegram code generation, masked link status and revocation.
  Codes are eight random digits, HMAC-hashed with a server-only secret, expire in 60–1800 seconds,
  are single-use, and a new code revokes earlier unused codes.
- Added a server-only failed-attempt ledger using an HMAC of the numerical Telegram principal.
  It never stores the raw code or message and rate-limits repeated guesses.
- Added takeover protections: a numerical Telegram identity cannot replace another owner's link,
  an owner must revoke before changing identities, and revocation blocks principal resolution.
- Added plugin v0.3.0 `/zlink`, which redeems the code through a direct restricted command path
  with gateway-supplied signed Telegram identity. Message text cannot set the owner.
- Linked identities replace the Stage 14 development owner at the FastAPI trust boundary, so web
  and Telegram resolve the same owner UUID. `source_channel` records `web`, `telegram`, `api`, or
  `administrative` only for provenance and has no authorization effect.
- Added the Stage 15 migration for source metadata and the server-only linking-attempt table. The
  full migration chain passed disposable PostgreSQL validation, the remote dry run listed only
  this migration, and it was applied successfully to the linked Supabase project.
- Added automated dashboard-auth, secret-boundary, linking expiry/reuse/guess/rate-limit,
  collision, revocation, cross-user takeover, direct-command and bidirectional cross-channel
  tests. Client source is scanned for prohibited backend secret names.
- Added patched PostCSS and Sharp overrides after npm audit found vulnerable transitive versions
  under Next 15. The narrow overrides preserved Next 15 compatibility and reduced npm audit to
  zero known vulnerabilities without a risky Next 16 migration.
- Agent-browser verified the landing and sign-in pages at port 3040 with no browser errors. The
  temporary frontend was stopped afterward. An authenticated real-user dashboard/link smoke is
  deliberately manual because Codex does not request or inspect user credentials or private codes.
- Added `docs/16-STAGE-15-DASHBOARD.md` with beginner-safe Auth, public frontend environment,
  plugin refresh, startup, linking, cross-channel and revocation steps.
- Corrected a Stage 15 runbook mismatch: the established health route was `/health`, while the
  new guide used `/api/v1/health`. FastAPI now keeps `/health` for Docker/older scripts and exposes
  a backward-compatible `/api/v1/health` alias. Both routes have regression coverage.
- Corrected the Stage 14-to-15 owner transition discovered during the first real `/zlink` smoke.
  The existing numerical Telegram ID was actively mapped to the old Stage 14 development user,
  while the new code belonged to the authenticated dashboard user, so the takeover guard correctly
  returned `identity_conflict`. A narrowly scoped local-development migration now accepts a valid
  code only for a link marked `development_config`, clears only its obsolete channel selection
  state, and changes that link to the code owner. Production and non-development links retain the
  strict conflict. Existing old-owner projects/experiments are neither moved nor deleted.

The owner subsequently completed the Stage 15 cross-channel, persistence, evidence/report,
revocation and re-linking smoke checks successfully.

### Stage 16 — channel-independent evidence and reports

- Expanded the immutable Evidence Envelope to v2 with exclusions, secondary metrics,
  calibration/error analysis, limitations, intended-use warning and reproducibility metadata.
- Added `zubepredict_core.reporting`, which generates one backend-owned artifact bundle from the
  verified envelope: EyeCare Evidence Card, evidence JSON, HTML, PDF, model card,
  reproducibility manifest and prediction CSV/XLSX where the task produces result rows.
- Added ReportLab 4.5.1 through the Python 3.11 uv lock for standards-compliant PDF output; the
  existing openpyxl dependency produces Excel exports.
- Moved report generation into the worker before completion. Web, Telegram and authenticated API
  delivery only look up the stored report; they never regenerate or rewrite it.
- Added report version, generic filename, MIME type, byte size, SHA-256, evidence hash and bounded
  integrity metadata to `public.reports` through
  `20260814165227_stage16_versioned_report_artifacts.sql`.
- Added owner-path, filename, size, SHA-256 and evidence-hash verification before each signed URL.
  Unfinished, cross-owner, missing and tampered artifacts fail safely.
- Expanded the dashboard to list every generated artifact and bumped the restricted Hermes plugin
  to v0.4.0 so its report tool can request each supported type. Exact signed URLs still bypass LLM
  transcription.
- Repaired two Stage 14 trusted-principal tests that accidentally queried the live linked Supabase
  state. Their mapper is now deterministic while allowed, denied and header-tampering assertions
  remain intact.
- Added Stage 16 tests for required report fields, actual PDF/Excel/CSV formats, prediction privacy,
  evidence/narrative tampering, identical web/Telegram/API artifact identity, unfinished reports,
  cross-owner denial and expired pending Telegram delivery.
- Verification: 223 pytest tests passed; Ruff passed; mypy passed across 48 source files; the
  Next.js 15.5.23 production build passed; and the disposable migration chain passed with 14 RLS
  policies and seven report-integrity columns.
- Added `docs/17-STAGE-16-REPORTING.md` for migration, plugin refresh and private owner smoke steps.

#### Stage 16 presentation correction — report version 2

- The first real owner smoke exposed a usability defect: the evidence values and integrity checks
  were correct, but the HTML printed Python dictionaries and the PDF placed serialized JSON into
  long paragraphs. This was technically complete but unsuitable for a non-technical reader.
- Bumped generated artifact presentation to report version 2. Existing version-1 rows and Storage
  objects remain immutable; new experiments write to a separate `/reports/v2/` path.
- Rebuilt the HTML and three-page PDF around an executive summary, selected-model/metric cards,
  plain-language measure explanations, ranked leaderboard, calibration/error review, prominent
  intended-use warning, limitations, reproducibility and integrity appendix. Raw evidence values
  are escaped and never rewritten by an LLM.
- Converted the EyeCare Evidence Card and Model Card from raw JSON/Markdown-style browser output
  into standalone responsive HTML documents. The authoritative Evidence Envelope and manifest
  remain pretty-printed JSON technical artifacts.
- Styled prediction XLSX with a Read me sheet, header colors, filters, frozen panes and readable
  widths. CSV remains standards-compatible and machine-readable.
- Replaced the dashboard's default JSON evidence block with a plain-language verified result card;
  the exact immutable envelope remains available under an optional technical disclosure.
- Added `scripts/preview_stage16_reports.py`, which creates a fully synthetic ignored preview bundle
  for safe visual inspection without Supabase or a full ML run.

That version-2 correction was not the final presentation: later owner review identified the HTML
usability issue recorded below. No public deployment was performed and Stage 17 was not started.

#### Stage 16 HTML usability correction — report version 3

- The owner confirmed that the version-2 PDF was clear and well styled, but the HTML Evidence
  Report, EyeCare Evidence Card and Model Card still felt too technical. The supplied HTML also
  exposed confusing character-encoding output in copied/plain-text representations.
- Bumped newly generated artifacts to report version 3. Version-1 and version-2 rows and Storage
  objects remain immutable; new experiments write to a separate `/reports/v3/` path.
- Reworked the full HTML report around three guided questions, plain-language score meaning,
  explicit non-claims, a visibly selected leaderboard winner and collapsed audit sections.
- Rebuilt the Evidence Card as a short-answer document with result, caution and next-step guidance.
  Rebuilt the Model Card as a non-technical factsheet with purpose, evaluation, responsible-use
  boundaries and an expandable technical appendix.
- Replaced decorative Unicode punctuation in the HTML templates with HTML entities so copied or
  differently decoded files do not show mojibake. Added responsive overflow protections and
  visually checked desktop and narrow-screen synthetic renders.
- The authoritative evidence values, hashes, report integrity, PDF presentation and cross-channel
  delivery architecture were not changed.
- Final verification after the version-3 correction: 223 pytest tests passed; Ruff passed; mypy
  passed across 48 source files; all generated HTML documents had one valid head/body structure
  and no detected mojibake markers; desktop and narrow-screen synthetic renders were inspected.

That version-3 correction was not sufficient in the real dashboard: the later browser-delivery
check below identified a platform delivery behavior that template inspection had not reproduced.
No public deployment was performed and Stage 17 was not started.

#### Stage 16 browser-delivery correction — report version 4

- The owner's version-3 files contained the intended CSS and plain-language design, but Chrome
  displayed their source code. Official Supabase documentation confirmed the root cause: Storage
  intentionally returns HTML files as plain text for security. More template styling alone could
  never fix the signed-Storage-URL behavior.
- Added authenticated report-content routes for the web dashboard and bearer-authenticated API.
  They enforce owner lookup, completed status, report-type/MIME allowlists, safe paths and names,
  byte size, artifact SHA-256 and Evidence Envelope hash before returning any bytes.
- Human HTML/PDF responses use the recorded MIME type with private no-store caching, nosniff,
  restrictive Content Security Policy, frame denial, no-referrer and safe inline disposition.
  Other formats retain attachment delivery. The dashboard fetches these verified bytes with the
  user's Supabase access token and opens HTML/PDF as browser Blob documents.
- Bumped newly generated artifacts to report version 4. The Reproducibility Manifest is now a
  styled HTML factsheet with a plain-language purpose, three-step reading guide, run summary,
  artifact policy, boundaries and expandable technical recipe. The Evidence Envelope remains the
  immutable JSON interchange artifact.
- Added CSP metadata to every generated HTML artifact so the restrictions remain effective when
  the dashboard opens a Blob URL. No script, remote resource, form or unescaped evidence value is
  allowed in those documents.
- Verification: 225 pytest tests passed; Ruff passed; mypy passed across 48 source files; the
  Next.js 15.5.23 production build passed; the authenticated-content/MIME mismatch tests passed;
  and all four version-4 human HTML artifacts were visually inspected as rendered pages.

No public deployment was performed. The owner subsequently accepted the corrected report
presentation and explicitly approved Stage 17, so this Stage 16 manual gate is complete.

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

### Hermes installation and runtime corrections

- The Windows installer began a very slow optional ffmpeg download. Because Stage 13 does
  not use audio, the owner stopped only the `winget` process. Hermes remained functional;
  ffmpeg can be installed later if voice work is explicitly requested.
- `hermes` was initially missing from the active PowerShell PATH. A refreshed shell found
  it, and project scripts also fall back to the managed executable under
  `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts`.
- `hermes doctor --fix` reported an older local state database without the `sessions`
  table and SQLite 3.38.4 WAL-reset exposure. The pinned repair helper safely skipped the
  replacement because it could not verify Windows virtual-environment file holders in the
  sandbox. Hermes source was not updated because that would violate the approved commit
  pin. Fresh-database behavior disables WAL defensively, but this local state limitation
  must be resolved through a supported upstream repair before production or valuable
  Hermes session history is stored.

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

## Stage 17 — security, privacy, quotas and Hermes hardening

Stage 17 was explicitly approved on 2026-08-15 and completed without public deployment.

Implemented:

- Kept Hermes core unmodified and pinned local startup to v0.20.0 commit
  `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`; the wrapper now refuses revision drift.
- Reviewed the official Hermes release/security material. v0.20.1 post-dates the pin and includes
  credential-surface, Telegram token-redaction and request-size hardening. Production deployment is
  blocked until a patched revision is compatibility-tested and deliberately re-pinned.
- Preserved the exact Telegram-only ZubePredict toolset and pre-LLM numerical allowlist/group
  denial. Trusted owner identity still comes only from gateway metadata and signed headers.
- Added Redis-backed per-owner API/Hermes, upload and daily experiment counters. Production quota
  backend failure is fail-closed; process-local fallback is development-only.
- Added retained-byte and active-experiment checks in the application plus Postgres advisory-lock
  triggers for race-safe storage/concurrency caps.
- Added explicit web and Telegram upload privacy attestation. When the production flag is enabled,
  upload cannot begin without confirmation of authorisation and removal of direct identifiers.
- Added bounded Telegram selection expiry. Expiry clears only conversation selections and never
  deletes or restarts backend experiments.
- Added report retention state, private dataset/report sweep indexes and a dry-run-first retention
  executor with an exact destructive confirmation phrase, failure rollback and audit events.
- Expanded audit coverage for web uploads, Constitution approval, experiment starts/cancellation
  and report access. Customer audit rows remain append-protected.
- Added request-size/security-header middleware, structured secret/JWT redaction, non-root Python
  containers and Git/Docker exclusions for Hermes runtime/conversation state.
- Added a security scan for tracked secrets/runtime state, frontend secret names, Python dependency
  consistency, npm advisories and optional/production-required Trivy scanning.
- Added `docs/18-STAGE-17-SECURITY.md` with credential-rotation incident procedures, privacy and
  consent boundaries, retention operation and the production checklist.

Correction discovered during implementation:

- The official Hermes v0.20.1 release appeared after the Stage 13 pin and contains a large security
  rollup. Silently upgrading would invalidate the tested plugin contract, while deploying v0.20.0
  would ignore known hardening. The safe decision is to keep local compatibility pinned and make
  patched-revision revalidation a blocking production checklist item.
- Application-only concurrent-job counting had a race between simultaneous requests. The Stage 17
  migration adds an owner-scoped PostgreSQL advisory lock and trigger so the authoritative limit is
  serialized at the database boundary as well.

No secrets were rotated by Codex because credential rotation is a manual account-owner action.
No retention deletion was executed. At the time Stage 17 code verification ended, no migration had
been pushed remotely; the owner subsequently applied and verified it on 2026-08-16 as recorded in
the current-status and migration-history sections above.

Verification: 233 tests, Ruff and mypy passed; Next.js production build passed; the complete
Stage 2–17 disposable PostgreSQL chain passed; npm and Python advisory audits found zero known
vulnerabilities; and the local secret/state scan passed. Trivy was not installed. The non-root
Docker rebuild hung beyond the timeout and was cancelled cleanly, so image build/scan remains a
manual production-gate item rather than a claimed pass.

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

- The owner reported that the authenticated Stage 15 dashboard/linking and cross-channel checks
  passed. Secrets and one-time codes remain owner-operated and must never be shared with Codex.
- The aiogram Telegram starter remains only as an explicitly disabled fallback. The primary
  Stage 14 route is the official Hermes Telegram gateway.
- The current local Hermes gateway remains owner-only. The database-backed linking mapper is
  production-safe at the API boundary, but multi-user gateway rollout and public deployment are
  intentionally deferred.
- Replay protection is in API-process memory. Multiple production API instances need a
  shared atomic nonce store.
- OpenRouter credentials and model selection are intentionally user-supplied. Automated
  tests use mocked transport and do not spend provider credits.
- The pinned Hermes runtime has the local SQLite repair limitation recorded above.
- Pinned Hermes v0.20.0 requires `agent.disabled_toolsets: [kanban]` globally to keep its
  non-configurable Kanban toolset out of Telegram; Kanban is therefore also unavailable in the
  developer CLI while Stage 14 isolation is active.
- Signed report URLs cannot be individually revoked after issuance by this application; revoking
  Telegram blocks new links, while an already-issued link remains usable until its five-minute
  expiry. This is why the TTL stays short.
- Redis quota enforcement is distributed, but the signed Hermes nonce cache remains process-local;
  multiple API instances require a shared atomic nonce store.
- Hermes v0.20.0 is behind the current v0.20.1 security rollup. It remains local-only until the
  plugin is tested and re-pinned against a patched release.
- Trivy was not installed during local verification. Container/image scanning is an explicit
  production blocker; npm audit completed separately with zero vulnerabilities.
- Retention execution is implemented but intentionally unscheduled. Staging deletion/restore,
  legal-hold and backup-retention exercises must precede scheduling.
- Render configuration is a restricted demonstration starting point; continuous reliable
  worker hosting and production monitoring are not complete.
- No claim has been made that model outputs are suitable for high-stakes decisions.
- The repository is a working Git checkout on `master` with an `origin` remote; inspect the
  current worktree before any future commit or push.

## Next planned work

The next roadmap item is **Stage 18 — restricted demonstration deployment and operational
monitoring**. Do not begin it until the owner has reviewed the Stage 17 manual security actions and
explicitly approves Stage 18.

Later stages remain:

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

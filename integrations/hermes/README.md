# ZubePredict Hermes integration

This directory is the tracked source of the Stage 13/14 Hermes plugin. Hermes is the outer
language-agent runtime; it is not a database client and does not execute ML directly.
Every tool call crosses the signed FastAPI boundary before the existing owner-scoped
repositories, LangGraph workflow, Dramatiq worker, and Supabase services are reached.

## Supported runtime

- Hermes Agent v0.20.0 (2026.8.3), installed from commit
  `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`.
- Hermes managed Python 3.11.0.
- ZubePredict API at `http://127.0.0.1:8040/api/v1` by default.
- OpenRouter model chosen through Hermes. It must support tool calling, reliable JSON,
  and a context window of at least 64k. The model ID is replaceable, not hard-coded.

## Install the tracked plugin

From the repository root:

```powershell
.\integrations\hermes\install-plugin.ps1
```

This copies the plugin to `%LOCALAPPDATA%\hermes\plugins\zubepredict` and enables it
without permission to override built-in tools. Re-run the script after tracked plugin
changes.

## Configure without exposing secrets

1. Copy the variable names in `config/hermes.env.example` into
   `%LOCALAPPDATA%\hermes\.env` and set values there.
2. Put the matching backend credential in the repository's ignored `.env` as
   `HERMES_SERVICE_KEYS=key-id:service-secret`.
3. Set `HERMES_DEV_PRINCIPAL_ID` in the repository `.env` to the same Supabase user UUID
   as `ZUBEPREDICT_HERMES_PRINCIPAL_ID` in the Hermes environment.
4. Run `hermes model`, choose OpenRouter, enter the key privately when prompted, and
   select a current model meeting the requirements above.
5. For Stage 14 Telegram, follow `docs/15-STAGE-14-TELEGRAM.md`. The BotFather token belongs
   only in `%LOCALAPPDATA%\hermes\.env`; never paste it into chat.

The development UUID mapper is intentionally rejected when `APP_ENV=production`. A
production deployment must replace it with an independently authenticated identity
mapping; changing the environment flag cannot silently promote the local design.

## Start and verify

Start Redis, the API, and worker using the root README. Then use a new terminal where the
Hermes environment is available:

```powershell
hermes plugins list
.\integrations\hermes\verify-stage13.ps1
hermes
```

Ask Hermes to check ZubePredict health. Project/dataset/experiment operations additionally
require a real Supabase user UUID that owns the referenced records. The automated test
suite uses mocked transport and does not spend OpenRouter credits.

For the owner-only Telegram polling gateway:

```powershell
.\integrations\hermes\configure-telegram.ps1
.\scripts\smoke-stage14-telegram.ps1
.\integrations\hermes\start-telegram-gateway.ps1
```

The startup wrapper rejects missing secrets, a mismatched numerical owner allowlist,
global/per-platform allow-all, a global allowlist, non-owner pairing approvals, group use
(hard-dropped by the official Telegram adapter before LLM dispatch),
and any Telegram toolset broader than `zubepredict`.

The pinned Hermes resolver automatically recovers default and Kanban tools from a plugin-only
list. `configure_telegram_tools.py` therefore makes the list authoritative with disabled STT and
`no_mcp` markers, globally suppresses the recovered Kanban toolset, and verifies the resolved
Telegram runtime contains only the ZubePredict plugin schemas.

## Security properties

- Seventeen allow-listed tools, including one-time account linking; unknown fields are forbidden.
- No tool accepts owner IDs, service keys, SQL, shell commands or arbitrary URLs. The one
  attachment tool accepts only a current resolved path beneath the Hermes document cache,
  transfers it to FastAPI and deletes the temporary copy.
- HMAC-SHA256 covers method, full path, timestamp, nonce, trusted principal, and body hash.
- Bounded clock skew and one-use nonces reduce replay risk.
- Owner scoping happens again in FastAPI repositories and Supabase RLS.
- Dataset-derived metadata is labelled untrusted and raw rows are not returned.
- Constitution approval, clarification versions, cancellation, and job idempotency are
  explicit.
- Evidence is hash-addressed and immutable; hallucinated numbers/models fall back to a
  deterministic summary.
- Plugin handlers always return bounded JSON errors and never leak exception or secret
  details to the model.
- Telegram sender ID and chat type come from Hermes task-local gateway context, not message
  content, and are covered by the signed FastAPI request.
- Telegram receives only the ZubePredict toolset; terminal/file/browser/code/cron/Git tools
  are not exposed.

The replay cache is process-local in Stage 13 development. Distributed replay protection,
production principal mapping, quotas, and full audit expansion belong to later hardening.

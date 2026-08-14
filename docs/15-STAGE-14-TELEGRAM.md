# Stage 14 — Hermes Agent Telegram gateway and secure channel integration

This guide is intentionally beginner-friendly. The Telegram route is local polling only. Nothing in
Stage 14 creates a public webhook or deployment.

## What was implemented

```text
Telegram private message
  → official Telegram Bot API
  → pinned Hermes Agent v0.20.0 Telegram gateway (local polling)
  → OpenRouter model inside Hermes
  → Telegram-isolated ZubePredict plugin tools
  → signed FastAPI boundary on port 8040
  → LangGraph + Redis/Dramatiq worker
  → private Supabase data, state and reports
```

Hermes obtains the numerical Telegram sender ID from Telegram metadata. The plugin reads that ID
from Hermes' task-local gateway context, not from the user's words. FastAPI verifies it as part of
the signed request. The owner ID, project IDs, dataset IDs and experiment ownership are never chosen
by the model.

## Manual stop point: create and configure your bot

Do not send the token to Codex, another person, a screenshot, GitHub, Next.js or Supabase.

1. Open the Telegram application.
2. Search for the verified **@BotFather** account. Confirm the username is exactly `@BotFather`.
3. Send `/newbot`.
4. Enter a display name, for example `ZubePredict AI Dev`.
5. Enter an available username ending in `bot`, for example `my_zubepredict_dev_bot`.
6. BotFather will send a token. Copy it privately. Do not paste it in this chat.
7. Find your numerical Telegram user ID. The Hermes documentation recommends messaging
   `@userinfobot`; it returns a number such as `123456789`. Do not use your `@username`.
8. Open this private file in Notepad:

   ```powershell
   notepad "$env:LOCALAPPDATA\hermes\.env"
   ```

9. Copy the variable names from
   `integrations\hermes\config\hermes.env.example` into that file. Set these two values privately:

   ```dotenv
   TELEGRAM_BOT_TOKEN=put_the_private_BotFather_token_here
   TELEGRAM_ALLOWED_USERS=put_your_numerical_Telegram_ID_here
   ZUBEPREDICT_TELEGRAM_OWNER_ID=put_the_same_numerical_Telegram_ID_here
   ```

10. Keep these restrictions exactly as shown:

    ```dotenv
    TELEGRAM_ALLOW_ALL_USERS=false
    GATEWAY_ALLOW_ALL_USERS=false
    GATEWAY_ALLOWED_USERS=
    TELEGRAM_GROUP_ALLOWED_USERS=
    TELEGRAM_GROUP_ALLOWED_CHATS=
    ZUBEPREDICT_TELEGRAM_UNSAFE_ALLOW_ALL=false
    ```

    Also set the attachment root to Hermes's managed Windows document cache (replace
    `YOUR_WINDOWS_USER` with your Windows account folder name):

    ```dotenv
    ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT=C:\Users\YOUR_WINDOWS_USER\AppData\Local\hermes\cache\documents
    ```

    Do not use `C:\Users\YOUR_WINDOWS_USER\.hermes\cache\documents`; the pinned managed Hermes
    installation does not cache Telegram documents there.

11. In the project `.env`, set the same numerical ID for backend verification:

    ```dotenv
    HERMES_TELEGRAM_OWNER_ID=put_your_numerical_Telegram_ID_here
    HERMES_TELEGRAM_UNSAFE_ALLOW_ALL=false
    HERMES_TELEGRAM_REPORT_TTL_SECONDS=300
    ```

12. Leave the project `.env` variable `TELEGRAM_BOT_TOKEN` blank. It belongs only to Hermes. That
    project variable exists for the disabled aiogram fallback and must not run with Hermes.
13. If the token ever leaks, open BotFather, use `/revoke`, create a replacement and update only the
    private Hermes `.env`.

Stop here until both private values are configured. Mocked tests can run without them; the real bot
cannot and should not.

## Apply the new Supabase migration

From the project root:

```powershell
npx supabase db push --dry-run --workdir infrastructure/supabase
npx supabase db push --workdir infrastructure/supabase
```

The new migration is `20260812132803_stage14_telegram_channel_state.sql`. It adds server-only account
links, resumable channel state and hashed one-time linking-code records. Read the list shown by the
CLI, choose **Yes**, and wait for `Finished supabase db push`.

## Configure the isolated Hermes Telegram toolset

Run once from the project root:

```powershell
.\integrations\hermes\configure-telegram.ps1
```

This reinstalls the current ZubePredict plugin and changes Telegram's toolset to only
`zubepredict`. It sets the official Telegram adapter's group response allowlist to the impossible
chat ID `0` and disables guest mode, so real group traffic is rejected before LLM dispatch. It also
disables speech-to-text because Stage 14 does not use audio. It does not read or print the bot
token. Internally, the pinned Hermes resolver needs a disabled STT configuration marker and a
`no_mcp` marker to make this plugin-only selection authoritative. The script also globally disables
Hermes's automatically recovered Kanban toolset; this is required by this pinned version and means
Kanban will not be available in the developer CLI while this restriction remains configured.

Check it:

```powershell
hermes config get platform_toolsets.telegram
```

The saved list contains `stt`, `zubepredict` and `no_mcp`, but STT is disabled and the other two
entries are control markers. The configure script verifies the resolved runtime result itself. For
an additional check, run `hermes tools list --platform telegram`. Only `zubepredict` may be shown
as enabled; terminal, file, browser, code, cron, GitHub, Kanban and unrelated MCP tools must not be
available.

## Start everything locally

Use five PowerShell terminals. Never use real patient data for this first test.

### Terminal 1 — Redis

If using Docker only for Redis:

```powershell
docker compose up -d redis
docker compose ps
```

If your compose file starts every service, instead use your existing validated compose workflow and
do not also start duplicate local API/worker processes.

### Terminal 2 — FastAPI on 8040

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
python -m uvicorn zubepredict_api.main:app --host 127.0.0.1 --port 8040
```

Check `http://127.0.0.1:8040/health` in your browser. It should report `healthy`.

### Terminal 3 — background worker

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
python -m dramatiq apps.worker.tasks --processes 1 --threads 2
```

The experiment lives in the backend and worker. Closing Telegram or restarting Hermes does not
restart or delete it.

### Terminal 4 — optional Next.js dashboard on 3040

Telegram does not require the frontend for Stage 14, but you may run it:

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI\apps\web
npm run dev -- --port 3040
```

### Terminal 5 — owner-only Hermes Telegram gateway

First run the no-secret-output preflight:

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\scripts\smoke-stage14-telegram.ps1
```

Then start local polling:

```powershell
.\integrations\hermes\start-telegram-gateway.ps1
```

The wrapper refuses missing secrets, mismatched numerical owner IDs, global allowlists, allow-all
flags, unsafe tools and non-owner pairing approvals. It never prints secret values.

## Real private owner smoke test

Use only the included safe synthetic sample dataset (or another synthetic CSV with no patient data).
In a private one-to-one chat with your bot:

1. Send `/start`. If the pinned gateway treats it as normal input, expect an introduction, privacy
   warning, available actions, and a decision-support/research limitation. Otherwise send `start`.
2. Send `Create a new project called Telegram smoke test.`
3. Attach the safe CSV and say `Upload this to the selected project.`
4. Say `I want to predict the target column.`
5. Ask `Profile the dataset and assess readiness.`
6. If the backend returns a clarification, answer the exact question.
7. Ask for the Experiment Constitution. Review task, target, prediction point, validation strategy,
   primary metric, exclusions, budget and intended-use warning.
8. Explicitly say `I confirm this exact Constitution version.`
9. Say `Start the experiment.` The bot must return `queued` quickly, not pretend it is completed.
10. Say `Show my experiment status.` Repeat safely until completed, failed, cancelled or clarification
    required. Duplicate checks must not create jobs.
11. If clarification is required, answer the exact backend question and confirm any task override.
12. Say `Show my verified results.` Values must come only from the evidence envelope.
13. Send `/zreport` for the deterministic report-delivery path. This command calls the same
    owner-authorized backend service but bypasses LLM transcription, so the signed URL is returned
    exactly. The URL expires in five minutes and contains no local storage path. Natural language
    such as `Give me the temporary evidence report.` remains supported through the report tool and
    Hermes lifecycle hooks.
14. To test cancellation on a separate queued/running synthetic experiment, say `Cancel my active
    experiment`, then explicitly confirm. It must never cancel another owner's experiment.
15. Send `/reset` or ask `reset this Telegram session`. This clears selections only; it does not
    delete backend experiments.
16. From another Telegram account, message the bot. It must refuse before OpenRouter or any tool.
17. Add the bot to no group. If it receives group traffic anyway, the official gateway drops it
    before LLM dispatch and the plugin independently rejects non-DM tool access.

Useful actions are `/help`, `/privacy`, `/new_project`, `/projects`, attachment upload, `/results`,
`/zreport`, `/cancel` and `/reset` when the pinned Hermes command registry exposes those names.
Natural-language forms call the same authorised tools. In this Hermes version `/status` is also a
built-in gateway command, so use `Show my experiment status` for product status.

## Stop safely

In the foreground Hermes terminal, press `Ctrl+C` once and wait for shutdown. Then stop worker and
API terminals with `Ctrl+C`. Stop Redis only if you started it for this test:

```powershell
docker compose stop redis
```

Do not run two gateways with the same bot token; Telegram rejects concurrent polling.

## Safe user-facing failures

- Backend unavailable: `ZubePredict is temporarily unavailable. Your existing experiment has not been restarted.`
- Invalid type: `That file type is not supported. Please upload CSV or XLSX.`
- Not authorised: `This Telegram account is not linked or authorised.`
- Report incomplete: `The report is not ready.`

Stack traces, SQL, environment paths, raw exceptions, API keys and tokens must never appear in chat.

## MVP limitations

- Real proactive completion notifications are not enabled. Use `Show my experiment status`.
- Private DMs only; groups are denied.
- The one-time linking schema/service exists, but the authenticated dashboard linking/revocation UI
  and production mapper are Stage 15 work.
- CSV, XLSX and Parquet are accepted by the upload contract. The beginner smoke test uses CSV; use
  Parquet only when the gateway preserves it reliably.
- The existing aiogram starter is a disabled fallback and must never run simultaneously with Hermes.

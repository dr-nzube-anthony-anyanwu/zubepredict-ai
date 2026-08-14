# Stage 15 — Unified dashboard, Auth and Telegram linking

Stage 15 gives the web dashboard and Hermes Telegram gateway one owner-scoped backend. A
`source_channel` value records where an item began, but never grants access. Supabase Auth and
database ownership remain authoritative.

## Implemented architecture

```text
Next.js browser -> Supabase Auth JWT -> FastAPI dashboard routes --+
                                                              |
Telegram -> Hermes signed sender ID -> FastAPI Hermes routes --+-> same Supabase rows
                                                              +-> same LangGraph jobs
                                                              +-> same evidence/reports
```

The browser receives only `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and
`NEXT_PUBLIC_SUPABASE_ANON_KEY`. It never receives the service-role key, database/Redis URL,
OpenRouter key, Telegram bot token, or Hermes service credential.

## One-time setup — do this carefully

### 1. Configure Supabase Auth URLs

1. Open your Supabase project dashboard in a browser.
2. Open **Authentication**.
3. Open **URL Configuration**.
4. Set **Site URL** to `http://localhost:3040` for local development.
5. Add `http://localhost:3040/auth/callback` to **Redirect URLs**.
6. Save.
7. Open **Providers**, select **Email**, and make sure email/password sign-in is enabled.
8. Keep email confirmation enabled if you want users to verify their email. For a local smoke
   test, remember to open the confirmation email before trying to sign in.

### 2. Configure the backend privately

Open the root `.env` file. Confirm these names exist. Never paste their values into chat:

```dotenv
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
TELEGRAM_LINKING_CODE_SECRET=
```

`TELEGRAM_LINKING_CODE_SECRET` must be a new random value of at least 32 characters. It is a
backend secret: do not prefix it with `NEXT_PUBLIC_`, do not copy it to Hermes, and do not commit
it. To generate one without printing it, run this from the repository root and paste the clipboard
contents directly into the root `.env`:

```powershell
$bytes = New-Object byte[] 48
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
$generator.GetBytes($bytes)
[Convert]::ToBase64String($bytes) | Set-Clipboard
$generator.Dispose()
Clear-Variable generator
Clear-Variable bytes
```

This form is compatible with Windows PowerShell installations whose older .NET runtime does not
provide the static `RandomNumberGenerator.Fill` method.

If a value was already configured for Stage 14 linking tests, keep it. Changing the secret makes
every outstanding unused link code invalid, which is useful during rotation.

### 3. Configure the browser-safe frontend file

Next.js runs from `apps/web`, so create or edit `apps/web/.env.local`. Put only these public values
inside it:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8040/api/v1
NEXT_PUBLIC_SUPABASE_URL=your_Supabase_project_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_Supabase_anon_key
```

The anon key is designed for browser use with RLS. The service-role key is not. Never place
`SUPABASE_SERVICE_ROLE_KEY`, `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, a Hermes credential,
`DATABASE_URL`, or `REDIS_URL` in this file.

### 4. Refresh the local Hermes plugin

Stop the foreground Hermes gateway with `Ctrl+C`, then run:

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\integrations\hermes\configure-telegram.ps1
```

This installs plugin v0.3.0 and adds the restricted `/zlink` command. It does not print the bot
token or service credential. Do not run the aiogram fallback.

## Start locally

Use separate PowerShell terminals.

### Terminal 1 — Redis

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
docker compose up redis
```

### Terminal 2 — FastAPI

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
python -m uvicorn zubepredict_api.main:app --host 127.0.0.1 --port 8040
```

Confirm `http://127.0.0.1:8040/api/v1/health` reports `healthy`. The original `/health` route
remains available for Docker and older scripts.

### Terminal 3 — worker

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
python -m dramatiq apps.worker.tasks
```

### Terminal 4 — frontend

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI\apps\web
npm run dev
```

Open `http://localhost:3040`.

### Terminal 5 — Hermes Telegram gateway

```powershell
cd C:\Users\User\Desktop\technologies\personal_technologies\ZubePredict-AI
.\integrations\hermes\start-telegram-gateway.ps1
```

Only the configured private owner DM is allowed during this local stage.

## Beginner account-linking smoke test

Use only synthetic data.

1. Open `http://localhost:3040` and click **Open workspace**.
2. Create an account with email and a strong password.
3. If Supabase sends a confirmation email, open it and confirm the account.
4. Sign in. The protected dashboard should open.
5. Create a project named `Stage 15 web smoke`.
6. Under **Telegram**, click **Connect Telegram**.
7. The dashboard shows an eight-digit code once. Do not send it to anyone else.
8. Open the private chat with your ZubePredict bot.
9. Send `/zlink 12345678`, replacing the example digits with the dashboard code.
10. The bot should say Telegram is connected.
11. Return to the dashboard and click **I sent the code — check link**.
12. The dashboard should show only a masked Telegram ID.
13. In Telegram, ask `Show my projects.` The web-created project must appear.
14. In Telegram, create a project or synthetic experiment.
15. Return to the dashboard and click **Refresh status**. The Telegram-created item must appear
    with a Telegram source badge but the same owner.
16. Upload the safe synthetic CSV through the dashboard.
17. Enter an objective, create a Constitution, review every field, tick the confirmation box, and
    queue it.
18. Close and reopen the page. The job must continue and its stored status must return.
19. When completed, open **Evidence** and then the temporary **Report**. Metrics must come from the
    evidence envelope; the report URL is short-lived.
20. Click **Revoke link**, confirm, and then try a Telegram product operation. It must refuse.
21. Re-linking must require a newly generated code. The old code must fail.

When upgrading from the Stage 14 single-owner smoke setup, the first valid `/zlink` may replace an
older `development_config` mapping. This is allowed only in local development, only for the
configured numerical owner ID, and only after a valid code proves control of the authenticated web
account. The obsolete Telegram selection state is cleared, but old projects, datasets, experiments,
evidence and reports are not moved or deleted. Production never enables this compatibility path.

Do not test guessing against the real bot. Automated tests cover expiry, reuse, collisions, failed
attempt rate limiting, revocation, and cross-user takeover.

## Verification commands

```powershell
.\.venv\Scripts\ruff.exe check apps\api\zubepredict_api packages\zubepredict_core integrations\hermes\plugin\zubepredict tests
.\.venv\Scripts\mypy.exe apps\api\zubepredict_api packages\zubepredict_core
.\.venv\Scripts\pytest.exe -q
.\scripts\validate-supabase-migration.ps1
cd apps\web
npm audit
npm run build
```

## Safe stop

Press `Ctrl+C` once in the frontend, Hermes, worker, API, and Redis terminals you started. Verify
ports afterward:

```powershell
netstat -ano | Select-String ':3040|:8040|:6379'
```

Stage 15 does not deploy publicly and does not begin Stage 16.

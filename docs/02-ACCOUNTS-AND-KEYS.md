# Accounts and Keys

Create only the accounts needed for the current stage. Do not pay for anything during the local foundation stages.

## Required now

### GitHub

Purpose: private source-code backup and version history.

1. Sign in to GitHub.
2. Create a new repository named `zubepredict-ai`.
3. Set it to **Private**.
4. Do not initialise it with a README because the project already has one.
5. Do not push `.env`.

### Supabase

Purpose: authentication, Postgres database and private file storage.

1. Create or sign in to a Supabase account.
2. Create a new project named `ZubePredict AI Development`.
3. Choose a strong database password and store it in a password manager.
4. Open **SQL Editor**.
5. Open `infrastructure/supabase/001_initial_schema.sql` in VS Code.
6. Copy the SQL and paste it into a new Supabase query.
7. Click **Run** once.
8. In Supabase project settings, copy the project URL and anonymous key into `.env`.
9. Put the service-role key only in the backend `.env`; never expose it as a `NEXT_PUBLIC_` value.
10. Follow `docs/04-STAGE-2-SUPABASE.md` to verify the migration and user isolation.

`001_initial_schema.sql` is an initial migration for a fresh project. Do not run it a
second time on a project where it has already succeeded.

## Required when adding Nous Hermes

### OpenRouter

Purpose: access Hermes or another compatible model without running it on your computer.

1. Create an OpenRouter account.
2. Create an API key specifically named for ZubePredict development.
3. Put it in `.env` as `OPENROUTER_API_KEY`.
4. Keep spending controls enabled.
5. Start with `OPENROUTER_MODEL=openrouter/free` while testing.

Set:

```text
LLM_PROVIDER=openrouter
```

The code must still work when this is returned to `template`.

### Ollama, optional

Purpose: run a quantized Nous Hermes model locally.

Do this only after the core application passes its tests. A 16GB computer may run the Q4 8B model, but Docker, the ML worker and the model will compete for memory.

After installing Ollama, the planned command is:

```powershell
ollama run hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M
```

Then set:

```text
LLM_PROVIDER=ollama
```

Close other heavy applications if Windows becomes slow. OpenRouter should remain the easier default.

## Required when adding Telegram

### Telegram BotFather

Purpose: create the ZubePredict bot identity and token.

1. Open Telegram.
2. Find the verified `@BotFather` account.
3. Start it and use `/newbot`.
4. Choose the display name.
5. Choose an available username ending in `bot`.
6. Copy the token into `.env` as `TELEGRAM_BOT_TOKEN`.
7. Never post or screenshot the token.
8. If a token is exposed, revoke it immediately through BotFather and create a new one.

## Required only for deployment

- Vercel: web interface.
- Render: demonstration API.
- Sentry: error monitoring.
- UptimeRobot: basic availability monitoring.

Do not configure deployment accounts until local Stages 0–8 are passing.

# ADR-014: Hermes Telegram trusted-channel boundary

- Status: accepted for Stage 14 local development
- Date: 2026-08-12
- Supersedes: no ADR; extends ADR-013

## Context

Stage 13 established a signed, least-privilege boundary between the Hermes plugin and FastAPI.
Stage 14 adds Telegram without allowing model-generated text to choose an owner, without exposing
Hermes' developer tools to a customer-facing chat, and without making conversation memory the
source of truth.

Hermes Agent v0.20.0 provides the official Telegram gateway, numerical sender allowlists, local
polling, per-chat session keys and task-local gateway context. In the pinned source,
`HERMES_SESSION_USER_ID`, `HERMES_SESSION_CHAT_TYPE` and `HERMES_SESSION_PLATFORM` are ContextVars
populated by the gateway outside the prompt. They are therefore suitable trusted channel inputs.

## Decision

1. The primary route is Telegram Bot API → Hermes Telegram gateway → OpenRouter → ZubePredict
   plugin → signed FastAPI boundary. The aiogram starter remains disabled fallback code only.
2. Stage 14 accepts private direct messages from exactly one configured numerical Telegram user ID.
   Usernames and message content do not participate in authorisation.
3. The plugin reads Hermes task-local gateway metadata and signs the channel name and channel
   principal into the Stage 13 canonical request. FastAPI verifies the signature, maps that Telegram
   ID to the configured development ZubePredict UUID, and refuses development mapping in production.
4. The Telegram platform toolset is exactly `zubepredict`; `hermes-telegram`, terminal, file,
   browser, code, database, cron and unrelated tools are excluded.
5. Supabase stores server-only Telegram account links and authoritative workflow state. RLS is
   enabled and privileges are revoked from `anon` and `authenticated`; only trusted service code
   can access these tables.
6. Attachment transfer is a restricted capability. The plugin may read only a resolved file under
   the Hermes documents cache, then always deletes it. FastAPI revalidates size, extension,
   content/signature and workbook archive structure, computes SHA-256, detects duplicates, assigns
   a UUID storage name and writes to the owner's private dataset path.
7. Report access is an owner-checked, audited, short-lived Supabase signed URL. No storage path or
   permanent public URL is returned.
8. Hermes proactive notifications are deferred in the MVP. Users query authoritative progress with
   natural-language status requests or the ZubePredict state/status tools. This avoids promising
   delivery that has not been proven against the real bot.

## Account-linking contract

The database and backend service support a production-oriented one-time linking contract:

1. An authenticated dashboard request creates an eight-digit code with a 1–30 minute bounded TTL.
2. Only an HMAC-SHA256 hash is stored; the plaintext code is returned once.
3. The Telegram bot submits the code with trusted gateway sender metadata.
4. The backend atomically consumes the unused, unexpired code and creates the channel link.
5. Reuse fails. The dashboard can revoke the link.

Stage 14 does not expose those endpoints or a public dashboard UI. Production authentication,
rate-limiting UX and revocation UI belong to Stage 15. The local owner mapping cannot run when
`APP_ENV=production`.

## Consequences

- A model prompt saying “my ID is 123” has no authorisation effect.
- Hermes restarts do not restart experiments or erase the selected backend resources.
- `/status` is a Hermes built-in gateway status command in the pinned version, so ZubePredict
  experiment status is supported by a plain request such as “show my experiment status.” A custom
  product slash-command registry can be added after the deployment topology is fixed.
- Existing Hermes pairing approvals are an alternate authorisation union. The safe startup wrapper
  refuses to start when it finds a non-owner Telegram approval and also rejects global allowlists or
  allow-all flags.
- The owner token and ID remain manual private configuration and are never placed in Git.

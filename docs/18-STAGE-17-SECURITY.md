# Stage 17 — security, privacy, quotas and Hermes hardening

Stage 17 hardens the existing unified web/API/Telegram system. It does not deploy anything and
does not modify Hermes core.

## Enforced controls

- Hermes remains pinned to v0.20.0 commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb` for local
  compatibility. The gateway wrapper verifies the Git revision before startup.
- Telegram resolves only the ZubePredict plugin toolset. Terminal, shell, filesystem, code,
  package installation, cron, generic MCP and unrelated tools remain unavailable.
- Numerical sender identity and chat type come from trusted gateway metadata, never message text.
- Missing allowlist, missing link state, unavailable link persistence, groups and unknown users
  fail before the product tool loop. Production never uses the development UUID mapper.
- API and Hermes requests have per-owner Redis counters. Production fails closed if quota state is
  unavailable; development may use a process-local fallback so local work remains possible.
- Upload count, private retained bytes, experiment starts and concurrent jobs are bounded.
- Worker time limits, cancellation polling, stale-job recovery, bounded retries and idempotency
  remain active.
- Uploads require an explicit authorisation/de-identification attestation when
  `REQUIRE_DATASET_PRIVACY_ATTESTATION=true`. This is an owner statement, not independent proof.
- Telegram selections expire after `TELEGRAM_SESSION_TTL_SECONDS`; expiry clears channel
  selections, never backend experiments.
- Dataset/report retention is private and status-controlled. The retention executor is dry-run by
  default and requires an exact phrase for destructive execution.
- Account linking, uploads/deletions, Constitution approval, experiment start/cancel and report
  access are audited without raw codes, message bodies or credentials.
- API responses receive no-store and defensive browser headers; structured logs redact common
  bearer/JWT/secret fields. Redaction is defense in depth, not a security boundary.

## Current Hermes security review

The official [Hermes v0.20.0 release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.3)
matches the reviewed local pin. Hermes v0.20.1 was released on August 13, 2026 and includes a broad
security-hardening round, including credential-surface fixes, Telegram transport token redaction
and HTTP body-size caps. The production gate is therefore **blocked** on deliberately validating
the ZubePredict plugin against a patched Hermes revision and updating the pin. Do not run
`hermes update` against a production gateway without completing that compatibility review.

Hermes documents that an in-process tool allowlist is not OS containment. A production or shared
gateway receiving untrusted content must use whole-process isolation, a non-root account, limited
mounts and restricted network egress. The gateway must not be publicly reachable without a VPN or
firewall boundary.

## Retention operation

Preview only:

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\python.exe .\scripts\run_retention_sweep.py
```

The preview prints counts only. Review legal holds and backups before execution. Execution is
intentionally explicit:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_retention_sweep.py --execute --confirm DELETE-EXPIRED-PRIVATE-ARTIFACTS
```

Do not schedule this command until staging restore/deletion exercises have passed. Do not place
expired raw clinical files in ordinary backups; backup retention must be documented separately.

## Local security checks

```powershell
.\scripts\security-scan.ps1
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe packages apps integrations
npm --prefix apps/web run build
.\scripts\validate-supabase-migration.ps1
```

The scan checks tracked Hermes state, common committed-secret patterns, prohibited frontend secret
names, Python dependency consistency and npm advisories. If Trivy is installed it also scans the
container configuration. Before deployment, Trivy is mandatory:

```powershell
.\scripts\security-scan.ps1 -RequireTrivy
```

## Production security checklist

- [ ] Validate and re-pin a currently patched Hermes revision; review its release notes and
  `SECURITY.md`.
- [ ] Run Hermes as a non-root, whole-process-isolated service with read-only/minimal mounts and
  restricted egress.
- [ ] Keep development, staging and production Telegram bots, OpenRouter keys, Supabase projects,
  linking secrets and Hermes service credentials completely separate.
- [ ] Rotate every production credential immediately before launch; configure overlapping Hermes
  key IDs only for the short rotation window, then remove the old key.
- [ ] Set `APP_ENV=production`, `ZUBEPREDICT_ENV=production`, explicit HTTPS CORS origins,
  `REQUIRE_DATASET_PRIVACY_ATTESTATION=true` and `QUOTA_FAIL_CLOSED=true`.
- [ ] Leave `HERMES_DEV_PRINCIPAL_ID`, backend `TELEGRAM_BOT_TOKEN`, all allow-all variables and
  global gateway allowlists empty/false.
- [ ] Replace the process-local Hermes nonce cache with a shared atomic one-use store before more
  than one API instance is used.
- [ ] Review Supabase Security Advisor, every exposed table, grants and all RLS policies. Confirm
  `anon` has no private-table access and service-role credentials never enter the browser.
- [ ] Push and verify the Stage 17 migration in staging first; rerun two-user RLS/storage tests.
- [ ] Configure Supabase Auth password policy, short JWT lifetime suitable for the risk, email
  controls, CAPTCHA/rate limits and session revocation procedures.
- [ ] Confirm private Storage buckets, owner UUID paths, signed URL expiry and no public URLs.
- [ ] Set customer quotas from measured capacity and monitor denial/error rates without dataset
  contents.
- [ ] Exercise cancellation, worker hard timeout, Redis outage, Supabase outage and stale-job
  recovery.
- [ ] Approve the privacy notice, intended-use limits, consent language, de-identification process,
  data-processing agreements and clinical governance with qualified legal/security reviewers.
- [ ] Run full tests, secret scan, dependency audits and mandatory Trivy image/config scan.
- [ ] Verify backups exclude Hermes conversations/runtime state and follow dataset/report deletion
  schedules, legal holds and restore tests.
- [ ] Configure append-only administrative audit export, alerting, clock synchronization and an
  incident contact/on-call path.
- [ ] Perform a staging penetration test covering BOLA/IDOR, upload parsing, prompt injection,
  account linking, replay, signed reports and cross-chat leakage.

## Incident response and credential rotation

Never paste an exposed value into an issue, chat, screenshot or log. Record only credential name,
environment, discovery time and rotation status.

### Telegram token

1. Stop the Hermes gateway.
2. In the verified BotFather chat use `/revoke` for the affected bot and issue a replacement.
3. Update only the environment-specific Hermes secret store.
4. Search logs and Git history without displaying the token; remove exposed artifacts.
5. Re-run the owner-only allowlist/startup checks and notify affected users if required.

### OpenRouter key

1. Stop Hermes requests, revoke the key in OpenRouter and create a least-privilege replacement.
2. Update only the appropriate Hermes environment/secret store.
3. Review provider usage for unexpected models, volume or cost and preserve safe audit evidence.

### Supabase service-role key

1. Treat this as full backend compromise: stop API/worker/report delivery and restrict network
   access.
2. Rotate the secret in Supabase, update backend/worker stores, revoke sessions if warranted and
   review Auth, Database and Storage logs.
3. Run ownership/RLS/integrity checks and assess notification/legal obligations before reopening.

### Hermes service credential

1. Add a new key ID/secret to the backend, update Hermes to use it, verify signed requests, then
   remove the old credential from both environments.
2. Review audit events for the old key ID and reject old nonces/signatures after the rotation
   window.

## Known blockers before public deployment

- Hermes v0.20.0 is no longer the newest patched release and must not be publicly deployed without
  the compatibility/re-pin review above.
- The signed-request nonce cache is process-local and supports only one API instance safely.
- Trivy is optional in local development but mandatory at the production gate.
- Privacy/clinical compliance requires human legal, security and clinical review; software checks
  cannot certify de-identification or regulatory compliance.

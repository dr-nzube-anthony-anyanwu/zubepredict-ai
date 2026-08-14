# Stage 13 — Nous Hermes grounded agent boundary

Stage 13 is complete. The accepted design and security reasoning are in
`docs/architecture/ADR-013-hermes-agent-boundary.md`; installation and private operator
configuration are in `integrations/hermes/README.md`.

The central rule is:

```text
Hermes -> signed strict FastAPI tools -> existing LangGraph/worker -> Supabase
```

Hermes is never a Supabase client, never receives the service-role key, and never receives
an owner ID from model arguments. The configured model is replaceable through OpenRouter.
Deterministic Python owns task decisions, training, validation, metrics, and evidence.

## Exit-gate proof

- Official native plugin layout and thirteen tool registrations.
- Strict schema and Pydantic validation with unknown-field rejection.
- Valid signature acceptance plus missing, invalid, expired, replayed, production-mapper,
  and different-principal denial tests.
- Full-path HMAC client test and stable backend-unavailable behavior.
- Idempotent experiment start with identifier-only queue arguments.
- Injection guard and immutable evidence fallback tests.
- Existing backend regression, static checks, frontend build, and Docker builds remain part
  of the final stage verification.

No Telegram setup belongs to this stage. The exact next prompt is
**Stage 14 — Secure Telegram Workflow**.

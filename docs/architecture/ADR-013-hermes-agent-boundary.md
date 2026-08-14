# ADR-013: Hermes agent boundary

Status: accepted for Stage 13 development, 2026-08-11.

## Decision

Use Nous Hermes as a replaceable outer agent runtime and OpenRouter as its configurable
model provider. Expose ZubePredict capabilities through a thin official Hermes plugin.
The plugin may call only a dedicated signed FastAPI surface:

```text
Hermes + tool-capable model
        |
        | 13 strict JSON tools, HMAC service authentication
        v
FastAPI /api/v1/hermes
        |
        +--> owner-scoped repositories --> Supabase/RLS
        |
        +--> Dramatiq identifiers only --> Stage 12 LangGraph worker
```

Hermes does not receive a Supabase service-role key, raw dataset path, database password,
SQL capability, arbitrary HTTP fetch tool, or local filesystem capability through this
plugin. The model cannot select the owner: the trusted principal is injected by plugin
configuration and included in the request signature.

## Tool surface

The plugin exposes health, project list/create, safe dataset profile, readiness,
constitution create/confirm, experiment start/status, clarification answer, cancellation,
evidence, and report metadata. These map one-to-one to explicit backend routes. Starting
an experiment reuses the Stage 12 durable experiment record and idempotent queue path.

No new Supabase table or Data API exposure was required. Constitution state lives in the
existing owned experiment configuration; the existing RLS and owner-scoped repository
queries remain authoritative.

## Trust and prompt-injection controls

Tool schemas and Pydantic models reject additional fields. Dataset names and columns are
bounded, labelled as untrusted, and never treated as instructions. A Hermes pre-LLM hook
adds ephemeral safety context. The backend remains authoritative for target membership,
task compatibility, constitution version, job state, and evidence.

Narrative output is subordinate to a frozen evidence envelope containing the dataset
fingerprint, constitution version, validation design, metrics, winner, warnings,
limitations, timestamp, and integrity hash. A narrative mentioning an unrecorded model or
number is replaced with a deterministic verified summary.

## Authentication decision

Development uses a rotated key set and HMAC-SHA256 over the request method, full URL path,
Unix timestamp, nonce, trusted principal UUID, and SHA-256 body hash. Signatures are
constant-time compared; timestamps expire; nonces are one-use per API process.

`HERMES_DEV_PRINCIPAL_ID` is an explicit local mapping and is refused in production. The
production solution must authenticate a human/session identity independently and map it
to the owner UUID. It must also use a shared replay store when multiple API instances are
deployed.

## Consequences

The model and Hermes can fail without corrupting deterministic evidence. Model/provider
replacement does not change backend contracts. Operations are slightly more verbose and
require matching local environment configuration. Telegram remains excluded until Stage
14, where its own identity and ownership design can be reviewed separately.

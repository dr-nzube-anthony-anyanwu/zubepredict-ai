# Stage 2: Supabase Persistence Foundation

Stage 2 supplies owner-scoped repository interfaces, Supabase adapters, the initial
Postgres schema, row-level security (RLS), and private Storage policies. It does not
yet connect the web UI or API routes to Supabase; those belong to later stages.

## Configuration

Keep these values in the root `.env` file:

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_DATASETS_BUCKET=datasets
SUPABASE_ARTIFACTS_BUCKET=artifacts
```

The service-role key is a backend secret. Never copy it into a `NEXT_PUBLIC_`
variable, browser bundle, log, screenshot, or source-control commit.

## Apply the initial migration

For a new Supabase project, open the SQL Editor, paste the complete contents of
`infrastructure/supabase/001_initial_schema.sql`, and run it once. The migration
creates the tables, indexes, explicit Data API privileges, RLS policies, profile
trigger, and private Storage buckets.

Do not rerun this initial migration after it succeeds. Future schema changes should
be new numbered migrations rather than edits executed against an existing database.

## Local migration validation

This command parses the migration in a disposable PostgreSQL 15 container and
checks that its RLS policies exist. It does not contact or modify Supabase.

```powershell
.\scripts\validate-supabase-migration.ps1
```

## Live two-user isolation smoke test

The smoke test authenticates two users, creates one project per user, verifies
that neither can read the other's row, and cleans up everything it created.

With a configured service-role key, it safely provisions and removes two temporary
users automatically:

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\python.exe scripts\smoke_supabase_stage2.py
```

Alternatively, omit the service-role key from the test process and provide all four
temporary environment variables for two existing confirmed test accounts:

```text
SUPABASE_TEST_USER_A_EMAIL
SUPABASE_TEST_USER_A_PASSWORD
SUPABASE_TEST_USER_B_EMAIL
SUPABASE_TEST_USER_B_PASSWORD
```

Never commit those passwords. Providing only part of a credential pair causes the
test to stop without running.

## Security model

- Authenticated browser/server sessions use the anon key plus the user's validated
  access token. RLS is the primary database boundary.
- Every user-owned query is also filtered by `owner_id` in the repository adapter.
- Model runs, reports, and audit rows are written only through trusted backend
  service repositories; authenticated users have read-only access to their rows.
- The service-role client bypasses RLS and therefore stays server-only. Its repository
  adapter still requires an explicit owner ID to reduce accidental cross-user access.
- Dataset and artifact objects are private and must live under the user's UUID folder.

The implementation follows Supabase's current recommendations for explicit
authenticated-role policies, cached `auth.uid()` checks, least-privilege grants, and
the additional Storage permissions required for safe upsert behavior.

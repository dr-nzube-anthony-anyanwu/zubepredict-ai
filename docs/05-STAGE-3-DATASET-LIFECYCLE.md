# Stage 3: Secure Dataset Lifecycle

Stage 3 adds authenticated direct uploads to the private `datasets` bucket,
server-side validation and fingerprinting, capped previews, retention metadata,
and an auditable delete operation. It does not build the dashboard upload UI;
that remains part of Stage 15.

## Apply the Stage 3 migration once

Open Supabase **SQL Editor**, paste the complete contents of:

```text
infrastructure/supabase/supabase/migrations/20260809003207_secure_dataset_lifecycle.sql
```

Run it once after `001_initial_schema.sql`. Do not rerun it after it succeeds.
The migration adds validated file metadata and retention fields, makes dataset
metadata writes server-only, and expands the private bucket MIME allowlist.

## Upload flow

All API requests require `Authorization: Bearer <the user's Supabase access token>`.

1. `POST /api/v1/datasets/upload-intents` with the owned project ID, original
   filename, and browser-reported content type.
2. Upload directly to Supabase Storage with the returned `storage_path` and
   `upload_token`. With `supabase-js`, use `uploadToSignedUrl(path, token, file)`.
3. `POST /api/v1/datasets/finalize` with the values returned by step 1.
4. Use the returned fingerprint, dimensions, retention state, and capped preview.
5. `DELETE /api/v1/datasets/{dataset_id}` removes the raw private object, records
   deletion audit events, and removes its metadata.

Signed upload credentials expire after two hours. Object paths are always
`<owner UUID>/<random UUID>.<validated extension>` and cannot be selected by users.

## Validation boundaries

- File transfer is processed in 64 KiB chunks and stops above `MAX_UPLOAD_MB`.
- Extension and MIME type must agree before a signed upload is issued.
- CSV must be UTF-8 text and must not carry a binary signature.
- `.xls` requires the OLE compound-file signature.
- `.xlsx` requires a real Excel ZIP structure and is checked for excessive
  expansion/compression ratios.
- Parquet requires both `PAR1` markers and is inspected through Parquet metadata.
- Datasets above `MAX_ROWS` or `MAX_COLUMNS` are rejected.
- Preview output is limited by `DATASET_PREVIEW_ROWS` and
  `DATASET_PREVIEW_COLUMNS`; these do not weaken the full dataset limits.
- SHA-256, byte size, detected format, MIME type, validation time, and retention
  expiry are computed by the trusted backend rather than accepted from the client.

## Verification

Validate every migration without touching Supabase:

```powershell
.\scripts\validate-supabase-migration.ps1
```

After applying the Stage 3 migration, run the disposable live lifecycle test:

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\python.exe scripts\smoke_supabase_stage3.py
```

The live test creates two temporary users, directly uploads a tiny CSV, verifies
cross-user isolation, performs the audited lifecycle deletion, and removes its
temporary audit rows, project, and users. It never prints credentials or tokens.

# Stage 16 — Channel-independent evidence, reports and artifact delivery

Stage 16 generates one authoritative artifact bundle in the background worker and exposes the
same private objects through the authenticated dashboard/API and the trusted linked Telegram
principal. Hermes never regenerates metrics or report bytes.

## Artifact architecture

```text
verified ML result + approved Experiment Constitution + dataset fingerprint
                              |
                              v
                  Evidence Envelope v2 (SHA-256)
                              |
                              v
              deterministic backend report generator
                              |
       +----------------------+----------------------+
       |                      |                      |
  private Storage       versioned reports      integrity metadata
       |                   database row         SHA-256/evidence hash
       +----------------------+----------------------+
                              |
              owner check + byte/hash verification
                              |
                 five-minute signed download
                   /            |             \
                 web         Telegram       Auth API
```

## Generated artifacts

Every newly completed Stage 16 experiment receives:

- `zubepredict-evidence-envelope.json` — immutable Evidence Envelope v2;
- `zubepredict-eyecare-evidence-card.html` — concise, styled EyeCare Evidence Card;
- `zubepredict-evidence-report.html` — human-readable HTML report;
- `zubepredict-evidence-report.pdf` — real PDF report;
- `zubepredict-model-card.html` — styled model card;
- `zubepredict-reproducibility-manifest.html` — readable experiment recipe and integrity reference;
- `zubepredict-predictions.csv` and `zubepredict-predictions.xlsx` when the task produces
  predictions, assignments or forecasts.

Prediction exports contain generated row identifiers/results and evidence metadata. They do not
copy source feature columns or patient-identifying filenames.

The reports carry the experiment ID, dataset fingerprint, Constitution version, task, target,
exclusions, validation strategy, primary/secondary metrics, leaderboard, selected model,
calibration/error analysis when available, limitations, intended-use warning, random seed,
software versions and integrity reference.

Human-facing report version 4 presents those same authoritative values as an executive summary,
guided reading steps, plain-language metric explanations, a highlighted winner, cautions and
limitations. Reproducibility, model settings and integrity identifiers are placed in clearly
labelled expandable technical sections. It never asks a reader to interpret a Python dictionary
or a single unbroken JSON paragraph. The reproducibility manifest is now a styled HTML factsheet;
the raw Evidence Envelope remains pretty-printed JSON for technical audit/interchange use.
Prediction Excel files add a Read me sheet, styled headings, filters, frozen headers and readable
column widths; prediction CSV remains a standards-compatible machine-readable export.

Version-1 through version-3 artifacts are immutable and are not overwritten. Restart the worker
after updating the code and create a new synthetic experiment to receive report version 4. A future
regeneration flow may create a higher report version, but it must never replace stored bytes under
an existing version.

## Security and integrity rules

- Reports are generated once by the worker from the verified evidence boundary.
- Storage paths begin with the owner and experiment UUID and remain in the private `artifacts`
  bucket.
- Database rows record report type/version, generic filename, MIME type, size, artifact SHA-256,
  Evidence Envelope hash and bounded generator metadata.
- A download request must find the experiment through an owner-scoped repository.
- The backend downloads and verifies the exact object bytes before every delivery.
- Path, filename, byte-size, SHA-256 or evidence-hash disagreement returns a safe integrity error.
- Web and authenticated API calls require a valid Supabase Auth session.
- Supabase Storage intentionally serves HTML as plain text. The dashboard therefore fetches owned,
  verified artifact bytes through FastAPI and opens a local browser Blob with the recorded MIME
  type. FastAPI adds no-store, nosniff, restrictive CSP, frame-denial and safe disposition headers.
- The authenticated API exposes the same content endpoint for clients that send a valid bearer
  token. It never exposes a service-role key or private Storage path.
- Telegram calls require the signed Hermes request and an active numerical Telegram account link.
- URLs expire after `HERMES_TELEGRAM_REPORT_TTL_SECONDS` (300 seconds by default).
- Revocation prevents issuance of new Telegram report links. A link already issued remains usable
  until its short expiry, so keep the TTL small.
- The plugin sends the exact backend URL outside LLM transcription. Hermes may explain verified
  evidence, but conflicting model names or numbers fall back to deterministic wording.

## Apply the Stage 16 migration

From the repository root, first preview the single pending migration:

```powershell
npx --yes supabase@2.110.0 db push --dry-run --workdir infrastructure/supabase
```

It should list:

```text
20260814165227_stage16_versioned_report_artifacts.sql
```

Then apply it:

```powershell
npx --yes supabase@2.110.0 db push --workdir infrastructure/supabase
```

Choose **Yes** only when the CLI lists that expected migration. Do not start a new experiment
until the migration has been applied because the worker writes the new report-integrity columns.

## Refresh Hermes after code changes

Stop the gateway with `Ctrl+C`, then run:

```powershell
.\integrations\hermes\configure-telegram.ps1
```

This installs restricted plugin v0.4.0 so Telegram can request HTML, PDF, model-card,
Evidence Card, predictions and reproducibility artifacts. It does not print secrets.

## Local owner smoke test

Use only `sample_data\readmission_demo.csv`.

After this correction, restart FastAPI and the Next.js frontend so the authenticated content route
and Blob viewer are active. Existing version-3 HTML Report, Evidence Card and Model Card objects can
then render through the dashboard without regeneration. Their version-3 reproducibility manifest
remains the original JSON artifact. Restart the worker and create a new synthetic experiment when
you want the complete version-4 bundle, including the styled HTML Reproducibility Manifest.

1. Start Redis, FastAPI, worker, frontend and Hermes using the Stage 15 terminal commands.
2. Sign in at `http://localhost:3040/dashboard`.
3. Create a new synthetic experiment after the Stage 16 migration is applied.
4. Wait for **Completed** and click **Refresh status**.
5. Confirm the experiment row offers Evidence Card, HTML, PDF, Model Card, predictions and the
   reproducibility manifest.
6. Click **Evidence** and note the evidence hash, selected model and primary metric.
7. Open HTML, PDF, Evidence Card, Model Card and Reproducibility Manifest. Confirm Chrome renders
   the human documents instead of displaying HTML source code and that they show the same evidence
   hash, model and metric where applicable.
8. Download CSV/XLSX. Confirm they contain synthetic prediction rows and evidence metadata.
9. In the private linked Telegram chat ask: `Give me the PDF report for my active experiment.`
10. Download it immediately. Confirm its report ID, SHA-256 and evidence hash match the dashboard
    metadata for the same PDF artifact.
11. Ask for the model card or reproducibility manifest and confirm the bot returns a temporary
    owner-authorized link rather than rewritten metrics.
12. Wait more than five minutes and confirm an old signed link no longer authorizes a fresh
    origin download. Do not post the URL anywhere.
13. Revoke Telegram in the dashboard and ask Telegram for another report. It must refuse before a
    new link is issued.
14. Re-link using a new one-time code if continued Telegram testing is required.

Do not test cross-user attacks or code guessing against the real bot. Automated tests cover
cross-owner access, tampered metadata/content, unfinished experiments, session isolation and
expired pending Telegram delivery.

## Automated verification

```powershell
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check apps\api\zubepredict_api packages\zubepredict_core integrations\hermes\plugin\zubepredict apps\worker tests
.\.venv\Scripts\mypy.exe apps\api\zubepredict_api packages\zubepredict_core
.\scripts\validate-supabase-migration.ps1
cd apps\web
npm run build
```

Stage 16 does not deploy publicly and does not begin Stage 17.

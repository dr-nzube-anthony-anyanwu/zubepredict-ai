# Stage 5: Data Quality and Leakage Guardian

Stage 5 adds a deterministic safety gate between task selection and model
training. It reports stable finding IDs, blocking errors, non-blocking warnings,
suggested feature exclusions, detected group/time structure, and an evidence
hash. It does not use an LLM to calculate or change findings.

## What it detects

- Suspected record and entity identifiers.
- Constant and at least 98% quasi-constant features.
- Duplicate rows.
- At least 80% missing features and at least 50% missing targets.
- High-cardinality categorical features.
- Exact target duplicates and near-perfect numeric or categorical proxies.
- Names suggesting information produced after the outcome.
- User-defined forbidden features.
- Repeated entity/group identifiers.
- Ordered date/time columns.

Default-risk features are suggested for exclusion and reported as warnings.
Exact target copies, extremely missing targets, forced constants/forbidden
features, grouped data without group-aware validation, and time-ordered data
without chronological validation block the existing shuffled tournament.

## Inspect a dataset

Send multipart form data to `POST /api/v1/analysis/quality`:

- `file`: CSV, Excel, or Parquet dataset.
- `target_column`: optional target name.
- `forbidden_features`: optional comma-separated feature names.
- `forced_features`: optional comma-separated risky features to retain.
- `acknowledged_risks`: optional comma-separated exact finding IDs.

The response separates `blocking_errors` and `warnings`. `can_train` is true
only when no blockers remain. The same guardian runs inside
`POST /api/v1/analysis/quick-tournament`, so the training path cannot bypass it.

## Risk acknowledgement

To retain a risky feature, first inspect the report. For example, forcing
`customer_id` produces the stable acknowledgement ID:

```text
suspected_identifier:customer_id
```

Send that exact ID in `acknowledged_risks` together with `customer_id` in
`forced_features`. Unknown, stale, or mismatched acknowledgement IDs are
rejected. The returned quality report records the acknowledgement and includes
it in the evidence hash.

Acknowledgement cannot override direct target duplication, constants,
user-forbidden features, or an unsafe validation strategy. These require the
data/configuration to be repaired or an appropriate group/time validation
strategy in a later stage.

## Run verification

No migration, account, API key, or new environment variable is required.

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\pytest.exe tests\unit\test_quality_guardian.py -q
.\scripts\test.ps1
```

The synthetic tests cover every Stage 5 finding family, stable evidence,
acknowledged and unacknowledged overrides, preprocessing exclusions, API
responses, and enforcement inside model training.

# Stage 6: Supervised Model Tournament

Stage 6 replaces the starter single-metric comparison with a reproducible,
leakage-safe classification and regression tournament. The Stage 5 guardian
runs first, and every preprocessing transformer is fitted only on a training
fold.

## Candidate planning

Every plan includes a simple dummy baseline. The planner records dataset rows,
usable/numeric/categorical columns, estimated encoded width, expected sparsity,
class imbalance, model-count limit, and compute budget.

Available candidates include:

- Dummy classifier/regressor baseline.
- Logistic or ridge regression.
- Random Forest and Extra Trees.
- XGBoost, LightGBM, and CatBoost when their optional dependencies are installed.

Advanced imports are guarded, so a missing optional library does not prevent
the baseline tournament from running. Candidate order changes for categorical
or sparse data and for constrained compute budgets. Failures retain their
completed fold scores, failure stage, and bounded error message without
stopping other candidates.

## Validation evidence

Classification uses shuffled stratified folds; regression uses shuffled
K-folds. Grouped and time-ordered data remain blocked by Stage 5 because these
strategies would be unsafe for them.

- Binary: average precision is primary, with ROC-AUC, recall, F1, balanced
  accuracy, Brier score, and log loss.
- Multiclass: macro F1 is primary, with balanced accuracy, one-vs-rest macro
  ROC-AUC, and log loss.
- Regression: RMSE is primary, with MAE and R-squared.

Each metric stores every fold value, mean, standard deviation, and an
approximate 95% confidence interval. The selected winner also returns full
out-of-fold predictions. Binary results include calibration bins, Brier score,
expected calibration error, and a threshold table from 0.10 through 0.90. The
recommended threshold maximizes out-of-fold F1 and is evidence, not an
automatic production policy.

The result records the random seed, candidate hyperparameters, validation fold
membership, and relevant Python/library versions.

## Winner fitting and safe artifacts

No candidate is fitted on the full dataset during comparison. After selection,
the best successful candidate is fitted once on all eligible rows. Pass a
`.skops` path as `winner_artifact_path` to save a bundle containing the fitted
pipeline, target-label mapping, feature/exclusion contract, seed, and software
versions.

The project does not write pickle or joblib model artifacts. Artifact metadata
contains SHA-256, byte size, format, and the types that `skops` considers
untrusted. Never load a user-supplied artifact or automatically trust every
reported type; loading and Supabase artifact transport belong to later stages.
The approach follows the official [scikit-learn persistence guidance](https://scikit-learn.org/stable/model_persistence.html)
and [skops secure-persistence guidance](https://skops.readthedocs.io/en/stable/persistence.html).

## Configuration and verification

Existing settings control resource use:

```text
MAX_CANDIDATE_MODELS=5
TRAINING_TIMEOUT_SECONDS=600
RANDOM_SEED=42
```

Install the locked ML environment and run the checks:

```powershell
.\.venv\Scripts\uv.exe sync --extra dev --extra ml
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\pytest.exe tests\unit\test_candidate_planner.py tests\unit\test_tournament.py -q
.\scripts\test.ps1
```

No database migration, account, or secret is required for Stage 6.

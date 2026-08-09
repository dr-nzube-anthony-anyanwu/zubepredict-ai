# Stage 10: Optuna Tuning and Compute Budgets

Stage 10 adds bounded hyperparameter tuning to supervised classification and
regression experiments. Existing Stage 6 untuned candidates always run first.
Their results remain unchanged in the leaderboard, including the required
simple baseline. A tuned result is an additional entry such as
`Ridge Regression (Optuna tuned)` and retains its untuned model name and Optuna
trial number.

Clustering, anomaly detection and forecasting continue to use their existing
bounded candidate searches from Stages 8 and 9. Stage 10 does not replace those
task-specific comparisons with generic hyperparameter search.

## Experiment configuration

Worker-run supervised experiments enable tuning by default. It can be disabled
or reduced per experiment:

```json
{
  "tuning_enabled": true,
  "tuning_trials": 6,
  "tuning_timeout_seconds": 90
}
```

All three fields are validated. Trial and time values must be positive integers;
strings, booleans, zero and negative values are rejected rather than coerced.

The server has separate experiment and owner-policy ceilings:

```dotenv
MAX_OPTUNA_TRIALS=10
OPTUNA_TIMEOUT_SECONDS=120
USER_MAX_OPTUNA_TRIALS=20
USER_OPTUNA_TIMEOUT_SECONDS=180
TUNING_MAX_CANDIDATES=2
```

The effective allocation is the lowest applicable requested, experiment and
owner-policy value. It is also limited by the time remaining in the overall
training budget. These harmless defaults are in `.env.example`; existing `.env`
files may omit them because the application supplies the same defaults.

## Dataset-aware reduction

The planner classifies datasets as small, medium, large or very large. Larger
datasets receive fewer base candidates, tuning candidates and trials. The
required baseline remains first even when a reduction applies. The requested
and effective counts, size band and reasons are returned as structured evidence.

The current thresholds are:

- small: fewer than 5,000 rows;
- medium: 5,000–19,999 rows;
- large: 20,000–49,999 rows;
- very large: at least 50,000 rows.

## Reproducibility and pruning

Each candidate uses a sequential `TPESampler` with the recorded application
seed. Trials use bounded search spaces and single-threaded estimators where the
candidate supports it. Classification maximizes its declared primary metric;
regression minimizes rolling cross-validation RMSE.

The median pruner receives the verified primary metric after each completed
cross-validation fold. A trial may stop only at that safe fold boundary. Every
completed, pruned and failed trial records its candidate, number, state,
parameters, metric, duration and last reported fold. Cancellation is checked
before trials and after folds.

Optuna documents seeded `TPESampler` use for reproducible sequential studies,
the independent `n_trials` and `timeout` controls, and the `report()` /
`should_prune()` pruning interface:

- [Optuna reproducibility guidance](https://optuna.readthedocs.io/en/stable/faq.html#how-can-i-obtain-reproducible-optimization-results)
- [Optuna Study.optimize limits](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.study.Study.html#optuna.study.Study.optimize)
- [Optuna efficient pruning](https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/003_efficient_optimization_algorithms.html#activating-pruners)

## Persistence and interpretation

The existing experiment result stores the tuning policy, effective budget and
trial history. The existing model-run rows store tuned provenance and selected
hyperparameters. The final `.skops` winner artifact includes the same tuning
summary. No new table, migration, bucket, account or secret is required.

Tuning and ranking use the same cross-validation design. This is useful for
model development but can make the selected score optimistic. The result warns
that a separate external holdout is needed before making final generalization
claims.

## Verification

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\pytest.exe tests\unit\test_tuning.py -q
.\scripts\test.ps1
```

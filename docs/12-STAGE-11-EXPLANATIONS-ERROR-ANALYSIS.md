# Stage 11: Explanations and Error Analysis

Stage 11 adds deterministic evidence after a supervised winner has been selected
and fitted. It does not let an LLM calculate, revise or invent explanations,
metrics, plots or segment results. Worker-run supervised experiments enable the
bounded analysis by default; direct library calls remain opt-in for backward
compatibility.

## Global and local explanations

The engine attempts SHAP against the fitted preprocessing/model pair. Only a
seeded sample is transformed for explanation, and a separately capped background
sample is used for masking. The result supports the current SHAP single-output
and multi-output array shapes, including class-specific local contributions.

If the selected estimator and SHAP are incompatible, the run does not fail.
Global evidence falls back to seeded permutation importance and local evidence
uses a one-feature-at-a-time reference perturbation. A constant dummy baseline
correctly reports zero effects instead of inventing importance.

Every local explanation records the source row index, actual value, predicted
value, explained output and largest signed contributions. Every explanation says
that model attribution is not a causal effect. SHAP documents its seeded generic
explainer and sampled background-masker interface in the
[official Explainer reference](https://shap.readthedocs.io/en/latest/generated/shap.Explainer.html).
The fallback follows scikit-learn's documented
[permutation-importance procedure](https://scikit-learn.org/stable/modules/generated/sklearn.inspection.permutation_importance.html).

## Error-analysis plot evidence

Plots are persisted as structured, renderer-independent JSON evidence rather
than trusted HTML or executable chart code. A later dashboard/report stage can
render the same verified coordinates and matrices.

Applicable outputs are:

- classification confusion matrix;
- binary ROC and precision-recall curves;
- binary probability calibration curve;
- regression residual and actual-versus-predicted plots;
- bounded three-point learning curve for every supported supervised task.

Diagnostic points come from the selected model's out-of-fold predictions. The
learning curve refits cloned pipelines with fold-fitted preprocessing and a
seeded split. Scikit-learn describes how training-set size curves diagnose data
and generalization behavior in its
[learning-curve guidance](https://scikit-learn.org/stable/modules/learning_curve.html).

## Segment error analysis

The engine compares out-of-fold error rate for classification and out-of-fold
mean absolute error for regression across up to three suitable low-cardinality
or binned numeric features. Very small groups are omitted. Columns whose names
identify common protected characteristics are skipped because Stage 11 is not a
fairness review.

Every segment result reports its row count, metric, overall metric, difference
from overall and a mandatory warning that the association is descriptive and
not causal. No segment is presented as a cause, protected-group conclusion or
verified real-world category.

## Bounds and configuration

Server-controlled defaults are:

```dotenv
EXPLANATION_MAX_SAMPLE_ROWS=200
EXPLANATION_BACKGROUND_ROWS=50
EXPLANATION_LOCAL_ROWS=5
EXPLANATION_MAX_FEATURES=15
EXPLANATION_PLOT_SAMPLE_ROWS=500
EXPLANATION_LEARNING_CURVE_ROWS=2000
```

An experiment may set `"explanations_enabled": false`, but it cannot raise these
server ceilings through its configuration. Cancellation is checked before and
after explanation phases and around the learning-curve operation.

## Private persistence

The worker uploads complete structured evidence to
`owner/experiment/job/evidence.json` in the existing private artifacts bucket.
The durable result summary contains only bounded counts, plot identifiers, top
global features, the private object path and a SHA-256 evidence digest. The
winner `.skops` bundle also contains the structured explanation and error
evidence needed to reproduce its model card later.

No new database migration, bucket, account or secret is required.

## Verification

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\pytest.exe tests\unit\test_explanations.py -q
.\scripts\test.ps1
```

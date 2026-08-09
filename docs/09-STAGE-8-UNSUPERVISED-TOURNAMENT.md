# Stage 8: Clustering and Anomaly Detection

Stage 8 adds deterministic exploratory analysis for explicit clustering and
anomaly-detection goals. It runs inside the existing Stage 7 worker; queue
messages remain limited to the experiment, owner, and job identifiers.

## Suitability and preprocessing

Before fitting, the Stage 5 guardian excludes identifiers, constants,
high-cardinality fields, and unsafe date/group columns. Numeric values are
median-imputed and standardised. Suitable categoricals are most-frequent
imputed and one-hot encoded with category and dense-matrix limits appropriate
for the local 16 GB development target.

Clustering requires at least 10 rows and anomaly detection requires at least
20. A run is blocked if no usable features remain, encoded width exceeds 500,
or the working matrix would exceed ten million values. All decisions and
exclusions are returned as structured evidence.

## Clustering tournament

The tournament compares multiple cluster-number candidates and includes:

- K-Means, including the simple `k=2` baseline;
- MiniBatch K-Means;
- Gaussian mixture, with AIC and BIC evidence;
- DBSCAN;
- HDBSCAN when the installed scikit-learn version provides it.

Each candidate records silhouette, Davies-Bouldin, Calinski-Harabasz, noise
coverage, three 80% row-subsample refits, and adjusted-Rand stability. Selection
uses a declared weighted internal-validity rule. Silhouette can favour convex
clusters, so it is not treated as truth and is combined with stability and
coverage. A failed candidate is recorded without stopping the tournament.

Segment descriptions contain only deterministic contrasts such as numeric
medians or categorical prevalence. Every description states that the segment
is algorithmically discovered, not a verified real-world group, causal
category, or ground truth.

## Anomaly tournament

The anomaly tournament includes a robust median/MAD score baseline, Isolation
Forest, and Local Outlier Factor. A bounded `contamination` value may be supplied
in the experiment configuration and defaults to `0.05`.

Because unlabelled data has no verified anomaly truth, selection does not claim
accuracy. It combines stability under small deterministic perturbations with
Jaccard agreement between the detectors' flagged row sets. Results include the
selected row-level scores and flags, but the durable experiment summary stores
only assignment counts rather than a potentially large row list. The complete
row-level assignments are written as a server-generated JSON artifact in the
existing private, owner-scoped Supabase artifacts bucket.

## Verification

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\pytest.exe tests\unit\test_unsupervised.py -q
.\scripts\test.ps1
```

No Stage 8 database migration, account, or new secret is required.

References: [scikit-learn clustering evaluation](https://scikit-learn.org/stable/modules/clustering.html#clustering-performance-evaluation),
[Gaussian mixture model selection](https://scikit-learn.org/stable/auto_examples/mixture/plot_gmm_selection.html),
and [outlier detection guidance](https://scikit-learn.org/stable/modules/outlier_detection.html).

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from zubepredict_core.evidence import build_evidence_envelope
from zubepredict_core.reporting import generate_report_bundle


def _metric(mean: float, deviation: float) -> dict[str, object]:
    margin = deviation * 1.96
    return {
        "mean": mean,
        "standard_deviation": deviation,
        "confidence_interval_95": [max(0.0, mean - margin), min(1.0, mean + margin)],
        "fold_values": [mean - deviation, mean, mean + deviation, mean, mean],
    }


def main() -> None:
    result_summary = {
        "task_type": "binary_classification",
        "target": "readmitted",
        "validation_strategy": "5-fold shuffled stratified cross-validation",
        "primary_metric": "average_precision",
        "winner": "Logistic Regression",
        "leaderboard": [
            {
                "model_name": "Logistic Regression",
                "status": "completed",
                "metrics": {
                    "average_precision": _metric(0.86, 0.03),
                    "roc_auc": _metric(0.89, 0.02),
                    "recall": _metric(0.81, 0.04),
                    "f1": _metric(0.83, 0.03),
                    "brier_score": _metric(0.12, 0.01),
                },
                "hyperparameters": {"C": 1.0, "class_weight": "balanced", "random_state": 42},
            },
            {
                "model_name": "Random Forest",
                "status": "completed",
                "metrics": {"average_precision": _metric(0.82, 0.04)},
            },
            {
                "model_name": "Baseline",
                "status": "completed",
                "metrics": {"average_precision": _metric(0.50, 0.0)},
            },
        ],
        "calibration": {
            "brier_score": 0.12,
            "expected_calibration_error": 0.06,
            "bins": [{"mean_predicted_probability": 0.2, "observed_positive_rate": 0.18}],
        },
        "threshold_analysis": {
            "recommended_threshold": 0.45,
            "recommendation_basis": "Highest out-of-fold F1; ties prefer the value nearest 0.5.",
        },
        "error_analysis_summary": {
            "plot_ids": ["confusion_matrix", "roc_curve", "calibration_curve"],
            "segment_count": 5,
            "protected_columns_skipped": ["age"],
        },
        "random_seed": 42,
        "software_versions": {
            "python": "3.11.0",
            "pandas": "2.3.3",
            "scikit-learn": "1.9.0",
        },
    }
    evidence = build_evidence_envelope(
        experiment_id=UUID("22222222-2222-4222-8222-222222222222"),
        dataset_fingerprint="a" * 64,
        constitution_version=3,
        result_summary=result_summary,
        warnings=["Synthetic preview data only."],
        constitution={
            "exclusions": ["patient_id"],
            "intended_use_warning": (
                "Decision support and research use only unless independently validated. "
                "Do not use this preview for clinical decisions."
            ),
        },
        generated_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )
    result = SimpleNamespace(
        out_of_fold_predictions=[
            {"row_index": "synthetic-001", "fold": 1, "actual": "no", "predicted": "no"},
            {"row_index": "synthetic-002", "fold": 1, "actual": "yes", "predicted": "yes"},
        ]
    )
    output_directory = Path("artifacts/stage16-report-preview")
    output_directory.mkdir(parents=True, exist_ok=True)
    for report in generate_report_bundle(evidence, result):
        (output_directory / report.filename).write_bytes(report.content)
    print(f"Generated synthetic report preview in {output_directory.resolve()}")


if __name__ == "__main__":
    main()

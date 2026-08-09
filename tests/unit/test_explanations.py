from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from zubepredict_core.data_engine.task_detector import detect_task
from zubepredict_core.ml_engine import explanations
from zubepredict_core.ml_engine.tournament import (
    TournamentCancelled,
    run_supervised_tournament,
)
from zubepredict_core.shared.schemas import TaskType

from apps.worker.tasks import _summary


def explanation_options() -> dict[str, object]:
    return {
        "explanations_enabled": True,
        "explanation_max_sample_rows": 30,
        "explanation_background_rows": 15,
        "explanation_local_rows": 3,
        "explanation_max_features": 6,
        "explanation_plot_sample_rows": 40,
        "explanation_learning_curve_rows": 80,
    }


def regression_frame(rows: int = 80) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal": range(rows),
            "region": ["north", "south", "west", "east"] * (rows // 4),
            "age": range(20, 20 + rows),
            "target": [index * 0.4 + (index % 5) for index in range(rows)],
        }
    )


def classification_frame(rows: int = 80) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal": range(rows),
            "channel": ["web", "store", "phone", "partner"] * (rows // 4),
            "target": ["yes" if index % 5 in {0, 1} else "no" for index in range(rows)],
        }
    )


def test_regression_has_bounded_global_local_and_residual_evidence() -> None:
    dataframe = regression_frame()
    result = run_supervised_tournament(
        dataframe,
        detect_task(dataframe, "target"),
        max_models=2,
        **explanation_options(),
    )

    assert result.explanations is not None
    assert result.error_analysis is not None
    assert result.explanations.sampled_rows <= 30
    assert len(result.explanations.local_explanations) == 3
    assert 0 < len(result.explanations.global_importance) <= 6
    assert result.explanations.method.startswith(("shap.", "permutation_"))
    assert {plot.kind for plot in result.error_analysis.plots} == {
        "residuals",
        "actual_vs_predicted",
        "learning_curve",
    }
    assert result.error_analysis.segments
    assert "age" in result.error_analysis.protected_columns_skipped
    assert all("not causal" in item.caveat for item in result.error_analysis.segments)


def test_binary_classification_has_confusion_roc_pr_calibration_and_learning_plots() -> None:
    dataframe = classification_frame()
    result = run_supervised_tournament(
        dataframe,
        detect_task(dataframe, "target"),
        max_models=2,
        **explanation_options(),
    )

    assert result.explanations is not None
    assert result.error_analysis is not None
    by_kind = {plot.kind: plot for plot in result.error_analysis.plots}
    assert {
        "confusion_matrix",
        "roc_curve",
        "precision_recall_curve",
        "calibration_curve",
        "learning_curve",
    } == set(by_kind)
    assert sum(sum(row) for row in by_kind["confusion_matrix"].matrix) == len(dataframe)
    assert set(by_kind["confusion_matrix"].labels) == {"no", "yes"}
    assert all(
        local.explained_output in {"no", "yes"} for local in result.explanations.local_explanations
    )


def test_constant_baseline_explanation_does_not_invent_feature_effects(tmp_path) -> None:
    dataframe = regression_frame()
    artifact = tmp_path / "winner.skops"
    result = run_supervised_tournament(
        dataframe,
        detect_task(dataframe, "target"),
        max_models=1,
        winner_artifact_path=artifact,
        **explanation_options(),
    )

    assert result.winner == "Baseline"
    assert result.explanations is not None
    assert result.explanations.method == "constant_baseline"
    assert all(item.importance == 0 for item in result.explanations.global_importance)
    assert all(not item.contributions for item in result.explanations.local_explanations)
    assert result.winner_artifact is not None
    assert result.winner_artifact.size_bytes == artifact.stat().st_size


def test_incompatible_shap_falls_back_without_losing_explanations(monkeypatch) -> None:
    monkeypatch.setattr(
        explanations,
        "_shap_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unsupported model")),
    )
    dataframe = regression_frame()
    result = run_supervised_tournament(
        dataframe,
        detect_task(dataframe, "target"),
        max_models=2,
        **explanation_options(),
    )

    assert result.explanations is not None
    assert result.explanations.method == ("permutation_importance_and_local_reference_perturbation")
    assert any("unsupported model" in warning for warning in result.explanations.warnings)
    assert result.explanations.local_explanations


def test_explanation_cancellation_is_promoted_to_tournament_cancellation() -> None:
    dataframe = regression_frame()
    checks = 0

    def cancel_during_explanations() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(TournamentCancelled, match="explanation analysis"):
        run_supervised_tournament(
            dataframe,
            detect_task(dataframe, "target"),
            max_models=1,
            cancellation_check=cancel_during_explanations,
            **explanation_options(),
        )


def test_worker_summary_keeps_full_evidence_private_and_hash_addressable() -> None:
    dataframe = regression_frame()
    result = run_supervised_tournament(
        dataframe,
        detect_task(dataframe, "target"),
        max_models=1,
        **explanation_options(),
    )

    summary = _summary(
        result,
        "owner/experiment/job/winner.skops",
        "owner/experiment/job/evidence.json",
        "a" * 64,
    )

    assert "explanations" not in summary
    assert "error_analysis" not in summary
    assert summary["explanation_summary"]["local_explanation_count"] == 3
    assert summary["error_analysis_summary"]["plot_ids"]
    assert summary["evidence_artifact_path"].endswith("evidence.json")
    assert summary["evidence_artifact_sha256"] == "a" * 64


def test_protected_name_matching_does_not_mistake_stage_for_age() -> None:
    features = pd.DataFrame(
        {
            "disease_stage": ["one", "two"] * 10,
            "age": range(20, 40),
        }
    )
    target = pd.Series([0, 1] * 10)
    predictions = np.asarray([0, 0, 1, 1] * 5)

    segments, skipped = explanations._segment_errors(
        features,
        target,
        predictions,
        TaskType.BINARY_CLASSIFICATION,
    )

    assert "age" in skipped
    assert "disease_stage" not in skipped
    assert any(item.feature == "disease_stage" for item in segments)

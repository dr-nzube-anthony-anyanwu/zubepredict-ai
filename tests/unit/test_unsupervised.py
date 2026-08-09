from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_blobs
from zubepredict_core.ml_engine import unsupervised
from zubepredict_core.ml_engine.tournament import TournamentCancelled
from zubepredict_core.ml_engine.unsupervised import (
    assess_unsupervised_suitability,
    run_unsupervised_tournament,
)
from zubepredict_core.shared.schemas import TaskDecision, TaskType


def decision(task_type: TaskType) -> TaskDecision:
    return TaskDecision(task_type=task_type, confidence=1, reasons=["explicit test intent"])


def test_suitability_excludes_identifiers_and_accepts_mixed_features() -> None:
    dataframe = pd.DataFrame(
        {
            "customer_id": [f"customer-{index}" for index in range(40)],
            "age": range(20, 60),
            "region": ["north", "south"] * 20,
        }
    )

    result = assess_unsupervised_suitability(dataframe, task_type=TaskType.CLUSTERING)

    assert result.can_run is True
    assert "customer_id" in result.excluded_columns
    assert result.numeric_columns == ["age"]
    assert result.categorical_columns == ["region"]
    assert result.estimated_encoded_features == 3


@pytest.mark.parametrize(
    ("task_type", "rows"),
    [(TaskType.CLUSTERING, 9), (TaskType.ANOMALY_DETECTION, 19)],
)
def test_suitability_rejects_too_few_rows(task_type: TaskType, rows: int) -> None:
    dataframe = pd.DataFrame({"feature": range(rows), "other": np.arange(rows) % 3})

    result = assess_unsupervised_suitability(dataframe, task_type=task_type)

    assert result.can_run is False
    assert "at least" in result.blockers[0]


def test_clustering_compares_cluster_counts_families_and_stability() -> None:
    values, _ = make_blobs(n_samples=90, centers=3, cluster_std=0.45, random_state=42)
    dataframe = pd.DataFrame(values, columns=["feature_a", "feature_b"])
    dataframe["channel"] = ["web", "store", "partner"] * 30

    result = run_unsupervised_tournament(
        dataframe,
        decision(TaskType.CLUSTERING),
        max_candidates=8,
    )

    completed = [score for score in result.leaderboard if score.status == "completed"]
    families = {score.family for score in result.leaderboard}
    kmeans_counts = {
        score.hyperparameters["n_clusters"]
        for score in result.leaderboard
        if score.family == "kmeans"
    }
    mixture_counts = {
        score.hyperparameters["n_components"]
        for score in result.leaderboard
        if score.family == "gaussian_mixture"
    }
    assert result.winner is not None
    assert len(kmeans_counts) > 1
    assert len(mixture_counts) > 1
    assert {
        "kmeans",
        "minibatch_kmeans",
        "gaussian_mixture",
        "dbscan",
        "hdbscan",
    } <= families
    assert completed[0].selection_score is not None
    assert len(completed[0].stability_scores) == 3
    assert len(result.assignments) == len(dataframe)
    assert result.segment_descriptions
    assert all("not a verified" in item.caveat for item in result.segment_descriptions)
    assert "internal evidence only" in result.selection_rule


def test_anomaly_tournament_includes_baseline_isolation_forest_and_lof() -> None:
    rng = np.random.default_rng(42)
    ordinary = rng.normal(0, 0.5, size=(95, 2))
    outliers = np.array([[8, 8], [9, -9], [-8, 9], [10, 10], [-10, -10]])
    dataframe = pd.DataFrame(np.vstack([ordinary, outliers]), columns=["x", "y"])

    result = run_unsupervised_tournament(
        dataframe,
        decision(TaskType.ANOMALY_DETECTION),
        contamination=0.05,
    )

    assert result.winner is not None
    assert {score.family for score in result.leaderboard} == {
        "robust_zscore",
        "isolation_forest",
        "local_outlier_factor",
    }
    assert sum(item.anomaly for item in result.assignments) == 5
    assert all(item.anomaly_score is not None for item in result.assignments)
    assert all(len(score.stability_scores) == 3 for score in result.leaderboard)
    assert "no ground-truth accuracy is implied" in result.selection_rule


def test_failed_clustering_candidate_is_recorded_without_crashing(monkeypatch) -> None:
    values, _ = make_blobs(n_samples=50, centers=2, random_state=42)
    dataframe = pd.DataFrame(values, columns=["x", "y"])
    original = unsupervised._clustering_candidates

    class Broken:
        def fit_predict(self, matrix):
            raise RuntimeError("candidate failed")

    def candidates(matrix, maximum):
        return [
            *original(matrix, maximum),
            unsupervised._Candidate("Broken", "broken", {}, lambda seed: Broken()),
        ]

    monkeypatch.setattr(unsupervised, "_clustering_candidates", candidates)

    result = run_unsupervised_tournament(
        dataframe,
        decision(TaskType.CLUSTERING),
        max_candidates=5,
    )

    failed = next(score for score in result.leaderboard if score.model_name == "Broken")
    assert result.winner is not None
    assert failed.status == "failed"
    assert failed.error == "candidate failed"


def test_unsupervised_tournament_honours_cancellation() -> None:
    dataframe = pd.DataFrame({"x": range(30), "y": np.arange(30) % 4})

    with pytest.raises(TournamentCancelled):
        run_unsupervised_tournament(
            dataframe,
            decision(TaskType.CLUSTERING),
            cancellation_check=lambda: True,
        )

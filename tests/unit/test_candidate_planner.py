from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.dummy import DummyClassifier
from zubepredict_core.ml_engine.candidate_planner import plan_candidates
from zubepredict_core.shared.schemas import TaskType


def factory() -> BaseEstimator:
    return DummyClassifier(strategy="prior")


def available(*names: str) -> dict[str, Callable[[], BaseEstimator]]:
    return {name: factory for name in names}


def test_planner_always_keeps_baseline_and_obeys_model_budget() -> None:
    features = pd.DataFrame({"age": range(100), "income": range(100, 200)})
    target = pd.Series([0] * 90 + [1] * 10)
    candidates = available(
        "Baseline",
        "Logistic Regression",
        "XGBoost",
        "LightGBM",
        "CatBoost",
        "Random Forest",
    )

    planned = plan_candidates(
        features,
        target,
        TaskType.BINARY_CLASSIFICATION,
        candidates,
        max_models=3,
        compute_budget_seconds=600,
    )

    assert list(planned.factories)[0] == "Baseline"
    assert len(planned.factories) == 3
    assert planned.evidence.imbalance_ratio == 0.111111
    assert any(
        entry.name == "Baseline" and entry.reason == "Required simple reference baseline."
        for entry in planned.evidence.candidates
    )


def test_planner_accounts_for_categoricals_sparsity_and_low_compute_budget() -> None:
    features = pd.DataFrame(
        {
            "numeric": range(100),
            "city": [f"city-{index % 60}" for index in range(100)],
            "segment": [f"segment-{index % 30}" for index in range(100)],
        }
    )
    target = pd.Series(["yes", "no"] * 50)
    candidates = available(
        "Baseline",
        "Logistic Regression",
        "XGBoost",
        "LightGBM",
        "CatBoost",
        "Random Forest",
    )

    normal = plan_candidates(
        features,
        target,
        TaskType.BINARY_CLASSIFICATION,
        candidates,
        max_models=4,
        compute_budget_seconds=600,
    )
    constrained = plan_candidates(
        features,
        target,
        TaskType.BINARY_CLASSIFICATION,
        candidates,
        max_models=3,
        compute_budget_seconds=30,
    )

    assert normal.evidence.categorical_features == 2
    assert normal.evidence.sparse_expected is True
    assert list(normal.factories)[:4] == [
        "Baseline",
        "Logistic Regression",
        "LightGBM",
        "Random Forest",
    ]
    assert list(constrained.factories) == [
        "Baseline",
        "Logistic Regression",
        "Random Forest",
    ]


def test_planner_reduces_candidates_for_large_datasets_and_keeps_baseline() -> None:
    features = pd.DataFrame({"signal": range(20_000)})
    target = pd.Series([0, 1] * 10_000)
    candidates = available(
        "Baseline",
        "Logistic Regression",
        "Random Forest",
        "Extra Trees",
        "XGBoost",
        "LightGBM",
    )

    planned = plan_candidates(
        features,
        target,
        TaskType.BINARY_CLASSIFICATION,
        candidates,
        max_models=6,
        compute_budget_seconds=600,
    )

    assert len(planned.factories) == 4
    assert list(planned.factories)[0] == "Baseline"
    assert planned.evidence.requested_max_models == 6
    assert planned.evidence.max_models == 4
    assert planned.evidence.dataset_size_band == "large"
    assert planned.evidence.reduction_reason is not None

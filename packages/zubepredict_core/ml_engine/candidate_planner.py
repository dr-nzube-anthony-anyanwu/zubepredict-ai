from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import pandas as pd
from sklearn.base import BaseEstimator

from zubepredict_core.shared.schemas import CandidatePlan, CandidatePlanEntry, TaskType


@dataclass(frozen=True)
class PlannedCandidates:
    factories: dict[str, Callable[[], BaseEstimator]]
    evidence: CandidatePlan


FAMILIES = {
    "Baseline": "baseline",
    "Logistic Regression": "linear",
    "Ridge Regression": "linear",
    "Random Forest": "bagged_trees",
    "Extra Trees": "bagged_trees",
    "XGBoost": "gradient_boosting",
    "LightGBM": "gradient_boosting",
    "CatBoost": "gradient_boosting",
}
OPTIONAL_MODULES = {
    "XGBoost": "xgboost",
    "LightGBM": "lightgbm",
    "CatBoost": "catboost",
}


def dataset_size_band(rows: int) -> Literal["small", "medium", "large", "very_large"]:
    if rows >= 50_000:
        return "very_large"
    if rows >= 20_000:
        return "large"
    if rows >= 5_000:
        return "medium"
    return "small"


def dataset_candidate_limit(rows: int, requested: int) -> tuple[int, str | None]:
    band = dataset_size_band(rows)
    caps = {
        "small": requested,
        "medium": min(requested, 5),
        "large": min(requested, 4),
        "very_large": min(requested, 3),
    }
    effective = caps[band]
    reason = None
    if effective < requested:
        reason = (
            f"Reduced the candidate count from {requested} to {effective} for a {band} "
            "dataset to respect local compute limits."
        )
    return effective, reason


def optional_model_availability() -> dict[str, bool]:
    return {
        name: importlib.util.find_spec(module) is not None
        for name, module in OPTIONAL_MODULES.items()
    }


def _preference_order(
    task_type: TaskType,
    *,
    has_categoricals: bool,
    sparse_expected: bool,
    low_budget: bool,
) -> list[str]:
    linear = "Ridge Regression" if task_type == TaskType.REGRESSION else "Logistic Regression"
    advanced = (
        ["CatBoost", "LightGBM", "XGBoost"]
        if has_categoricals
        else ["XGBoost", "LightGBM", "CatBoost"]
    )
    if sparse_expected:
        advanced = ["LightGBM", "XGBoost", "CatBoost"]
    trees = ["Random Forest", "Extra Trees"]
    if low_budget:
        return ["Baseline", linear, *trees, *advanced]
    if has_categoricals:
        return ["Baseline", linear, advanced[0], "Random Forest", *advanced[1:], "Extra Trees"]
    return ["Baseline", linear, "XGBoost", *trees, "LightGBM", "CatBoost"]


def plan_candidates(
    features: pd.DataFrame,
    target: pd.Series,
    task_type: TaskType,
    available_factories: dict[str, Callable[[], BaseEstimator]],
    *,
    max_models: int,
    compute_budget_seconds: int,
) -> PlannedCandidates:
    requested_max_models = max_models
    max_models, reduction_reason = dataset_candidate_limit(len(features), max_models)
    numeric_count = len(features.select_dtypes(include="number").columns)
    categorical_columns = [
        column
        for column in features.columns
        if column not in features.select_dtypes(include="number")
    ]
    categorical_count = len(categorical_columns)
    estimated_encoded = numeric_count + sum(
        min(int(features[column].nunique(dropna=True)), 100) for column in categorical_columns
    )
    sparse_expected = bool(
        categorical_count
        and (
            estimated_encoded >= max(50, len(features.columns) * 3)
            or categorical_count > numeric_count
        )
    )
    imbalance_ratio: float | None = None
    if task_type in {TaskType.BINARY_CLASSIFICATION, TaskType.MULTICLASS_CLASSIFICATION}:
        counts = target.value_counts()
        if not counts.empty:
            imbalance_ratio = round(float(counts.min() / counts.max()), 6)

    preference = _preference_order(
        task_type,
        has_categoricals=categorical_count > 0,
        sparse_expected=sparse_expected,
        low_budget=compute_budget_seconds <= 60 or len(features) >= 20_000,
    )
    ordered_names = [name for name in preference if name in available_factories]
    ordered_names.extend(name for name in available_factories if name not in ordered_names)
    selected_names = ordered_names[:max_models]
    selected = {name: available_factories[name] for name in selected_names}

    entries: list[CandidatePlanEntry] = []
    for name in ordered_names:
        is_selected = name in selected
        reason = "Selected within the model and compute budget."
        if name == "Baseline":
            reason = "Required simple reference baseline."
        elif not is_selected:
            reason = "Available but omitted by the model-count or compute budget."
        elif name == "CatBoost" and categorical_count:
            reason = "Selected because categorical features are present."
        elif name in {"LightGBM", "XGBoost"} and sparse_expected:
            reason = "Selected for the estimated sparse encoded feature space."
        entries.append(
            CandidatePlanEntry(
                name=name,
                family=FAMILIES.get(name, "custom"),
                selected=is_selected,
                reason=reason,
            )
        )
    availability = optional_model_availability()
    for name, is_available in availability.items():
        if name not in available_factories:
            entries.append(
                CandidatePlanEntry(
                    name=name,
                    family=FAMILIES[name],
                    selected=False,
                    reason=(
                        "Optional dependency is not installed."
                        if not is_available
                        else "Estimator was unavailable for this task configuration."
                    ),
                )
            )

    return PlannedCandidates(
        factories=selected,
        evidence=CandidatePlan(
            rows=len(features),
            usable_features=len(features.columns),
            numeric_features=numeric_count,
            categorical_features=categorical_count,
            estimated_encoded_features=estimated_encoded,
            sparse_expected=sparse_expected,
            imbalance_ratio=imbalance_ratio,
            compute_budget_seconds=compute_budget_seconds,
            max_models=max_models,
            requested_max_models=requested_max_models,
            dataset_size_band=dataset_size_band(len(features)),
            reduction_reason=reduction_reason,
            candidates=entries,
        ),
    )

from __future__ import annotations

import hashlib
import importlib.util
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

from zubepredict_core.data_engine.quality_guardian import assess_data_quality
from zubepredict_core.ml_engine.candidate_planner import plan_candidates
from zubepredict_core.ml_engine.explanations import (
    ExplanationCancelled,
    build_explanation_and_error_analysis,
)
from zubepredict_core.ml_engine.preprocessing import PreprocessingPlan, build_preprocessor
from zubepredict_core.ml_engine.tuning import (
    TuningPruned,
    resolve_tuning_budget,
    run_optuna_tuning,
)
from zubepredict_core.shared.schemas import (
    ArtifactManifest,
    CalibrationBin,
    CalibrationSummary,
    ErrorAnalysisEvidence,
    ExperimentResult,
    ExplanationEvidence,
    FoldScore,
    MetricSummary,
    ModelScore,
    OutOfFoldPrediction,
    TaskDecision,
    TaskType,
    ThresholdAnalysis,
    ThresholdPoint,
    TuningSummary,
)


@dataclass
class _CandidateEvaluation:
    score: ModelScore
    oof_predictions: np.ndarray[Any, Any] | None = None
    oof_probabilities: np.ndarray[Any, Any] | None = None
    fold_assignments: np.ndarray[Any, Any] | None = None
    classes: list[Any] | None = None


class TournamentCancelled(RuntimeError):
    """Raised at a safe boundary when an experiment cancellation is requested."""


def _has_module(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _classification_models(seed: int) -> dict[str, Callable[[], BaseEstimator]]:
    models: dict[str, Callable[[], BaseEstimator]] = {
        "Baseline": lambda: DummyClassifier(strategy="prior"),
        "Logistic Regression": lambda: LogisticRegression(
            max_iter=1_000, class_weight="balanced", random_state=seed
        ),
        "Random Forest": lambda: RandomForestClassifier(
            n_estimators=160,
            random_state=seed,
            class_weight="balanced",
            n_jobs=1,
        ),
        "Extra Trees": lambda: ExtraTreesClassifier(
            n_estimators=160,
            random_state=seed,
            class_weight="balanced",
            n_jobs=1,
        ),
    }
    if _has_module("xgboost"):

        def xgboost_classifier() -> BaseEstimator:
            from xgboost import XGBClassifier

            return XGBClassifier(
                n_estimators=160,
                learning_rate=0.05,
                max_depth=6,
                subsample=0.9,
                colsample_bytree=0.9,
                eval_metric="logloss",
                random_state=seed,
                n_jobs=1,
            )

        models["XGBoost"] = xgboost_classifier
    if _has_module("lightgbm"):

        def lightgbm_classifier() -> BaseEstimator:
            from lightgbm import LGBMClassifier

            return LGBMClassifier(
                n_estimators=160,
                learning_rate=0.05,
                class_weight="balanced",
                random_state=seed,
                n_jobs=1,
                verbosity=-1,
            )

        models["LightGBM"] = lightgbm_classifier
    if _has_module("catboost"):

        def catboost_classifier() -> BaseEstimator:
            from catboost import CatBoostClassifier

            return CatBoostClassifier(
                iterations=160,
                learning_rate=0.05,
                depth=6,
                auto_class_weights="Balanced",
                random_seed=seed,
                thread_count=1,
                verbose=False,
                allow_writing_files=False,
            )

        models["CatBoost"] = catboost_classifier
    return models


def _regression_models(seed: int) -> dict[str, Callable[[], BaseEstimator]]:
    models: dict[str, Callable[[], BaseEstimator]] = {
        "Baseline": lambda: DummyRegressor(strategy="mean"),
        "Ridge Regression": lambda: Ridge(alpha=1.0),
        "Random Forest": lambda: RandomForestRegressor(
            n_estimators=160, random_state=seed, n_jobs=1
        ),
        "Extra Trees": lambda: ExtraTreesRegressor(n_estimators=160, random_state=seed, n_jobs=1),
    }
    if _has_module("xgboost"):

        def xgboost_regressor() -> BaseEstimator:
            from xgboost import XGBRegressor

            return XGBRegressor(
                n_estimators=160,
                learning_rate=0.05,
                max_depth=6,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="reg:squarederror",
                random_state=seed,
                n_jobs=1,
            )

        models["XGBoost"] = xgboost_regressor
    if _has_module("lightgbm"):

        def lightgbm_regressor() -> BaseEstimator:
            from lightgbm import LGBMRegressor

            return LGBMRegressor(
                n_estimators=160,
                learning_rate=0.05,
                random_state=seed,
                n_jobs=1,
                verbosity=-1,
            )

        models["LightGBM"] = lightgbm_regressor
    if _has_module("catboost"):

        def catboost_regressor() -> BaseEstimator:
            from catboost import CatBoostRegressor

            return CatBoostRegressor(
                iterations=160,
                learning_rate=0.05,
                depth=6,
                loss_function="RMSE",
                random_seed=seed,
                thread_count=1,
                verbose=False,
                allow_writing_files=False,
            )

        models["CatBoost"] = catboost_regressor
    return models


def _python_value(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _parameter_value(value: Any) -> Any:
    value = _python_value(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_parameter_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _parameter_value(item) for key, item in value.items()}
    return repr(value)


def _software_versions() -> dict[str, str]:
    packages = (
        "python",
        "numpy",
        "pandas",
        "scikit-learn",
        "xgboost",
        "lightgbm",
        "catboost",
        "optuna",
        "skops",
    )
    versions: dict[str, str] = {}
    for package in packages:
        if package == "python":
            import platform

            versions[package] = platform.python_version()
            continue
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    return versions


def _confidence_interval(values: list[float]) -> tuple[float, float]:
    mean = float(np.mean(values))
    if len(values) < 2:
        return (mean, mean)
    margin = 1.96 * float(np.std(values, ddof=1)) / math.sqrt(len(values))
    return (mean - margin, mean + margin)


def _metric_summaries(folds: list[FoldScore]) -> dict[str, MetricSummary]:
    names = list(folds[0].metrics) if folds else []
    summaries: dict[str, MetricSummary] = {}
    for name in names:
        values = [fold.metrics[name] for fold in folds]
        summaries[name] = MetricSummary(
            mean=float(np.mean(values)),
            standard_deviation=float(np.std(values)),
            confidence_interval_95=_confidence_interval(values),
            fold_values=values,
        )
    return summaries


def _probabilities(
    pipeline: Pipeline, features: pd.DataFrame
) -> tuple[np.ndarray[Any, Any], list[Any]]:
    if not hasattr(pipeline, "predict_proba"):
        raise ValueError("This classifier does not provide probabilities required for scoring.")
    probabilities = np.asarray(pipeline.predict_proba(features), dtype=float)
    classes = list(pipeline.classes_)
    return probabilities, classes


def _classification_metrics(
    actual: pd.Series,
    predicted: np.ndarray[Any, Any],
    probabilities: np.ndarray[Any, Any],
    classes: list[Any],
    task_type: TaskType,
    positive_label: Any | None,
) -> dict[str, float]:
    if task_type == TaskType.BINARY_CLASSIFICATION:
        if positive_label not in classes:
            raise ValueError("The configured positive class was absent from a validation fold.")
        positive_index = classes.index(positive_label)
        actual_binary = (actual.to_numpy() == positive_label).astype(int)
        predicted_binary = (predicted == positive_label).astype(int)
        positive_probability = probabilities[:, positive_index]
        return {
            "average_precision": float(
                average_precision_score(actual_binary, positive_probability)
            ),
            "roc_auc": float(roc_auc_score(actual_binary, positive_probability)),
            "recall": float(recall_score(actual_binary, predicted_binary, zero_division=0)),
            "f1": float(f1_score(actual_binary, predicted_binary, zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(actual_binary, predicted_binary)),
            "brier_score": float(brier_score_loss(actual_binary, positive_probability)),
            "log_loss": float(log_loss(actual, probabilities, labels=classes)),
        }
    return {
        "f1_macro": float(f1_score(actual, predicted, average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(actual, predicted)),
        "roc_auc_ovr_macro": float(
            roc_auc_score(actual, probabilities, labels=classes, multi_class="ovr", average="macro")
        ),
        "log_loss": float(log_loss(actual, probabilities, labels=classes)),
    }


def _regression_metrics(actual: pd.Series, predicted: np.ndarray[Any, Any]) -> dict[str, float]:
    return {
        "root_mean_squared_error": float(mean_squared_error(actual, predicted) ** 0.5),
        "mean_absolute_error": float(mean_absolute_error(actual, predicted)),
        "r2": float(r2_score(actual, predicted)),
    }


def _evaluate_candidate(
    name: str,
    factory: Callable[[], BaseEstimator],
    features: pd.DataFrame,
    target: pd.Series,
    preprocessing: PreprocessingPlan,
    splits: list[tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]],
    task_type: TaskType,
    primary_metric: str,
    positive_label: Any | None,
    fold_progress: Callable[[int, float], None] | None = None,
) -> _CandidateEvaluation:
    started = time.perf_counter()
    fold_scores: list[FoldScore] = []
    oof_predictions = np.empty(len(target), dtype=object)
    fold_assignments = np.full(len(target), -1, dtype=int)
    oof_probabilities: np.ndarray[Any, Any] | None = None
    global_classes = list(np.unique(target)) if task_type != TaskType.REGRESSION else None
    parameters: dict[str, Any] = {}

    try:
        prototype = factory()
        parameters = (
            {
                str(key): _parameter_value(value)
                for key, value in prototype.get_params(deep=False).items()
            }
            if hasattr(prototype, "get_params")
            else {}
        )
        for fold_number, (train_indices, validation_indices) in enumerate(splits, start=1):
            train_features = features.iloc[train_indices]
            validation_features = features.iloc[validation_indices]
            train_target = target.iloc[train_indices]
            validation_target = target.iloc[validation_indices]
            pipeline = Pipeline(
                [("preprocessor", clone(preprocessing.transformer)), ("model", clone(prototype))]
            )
            fit_started = time.perf_counter()
            pipeline.fit(train_features, train_target)
            fit_seconds = time.perf_counter() - fit_started
            predict_started = time.perf_counter()
            predicted = np.asarray(pipeline.predict(validation_features))
            if task_type == TaskType.REGRESSION:
                metrics = _regression_metrics(validation_target, predicted)
            else:
                fold_probabilities, fold_classes = _probabilities(pipeline, validation_features)
                if global_classes is None:
                    raise ValueError("Classification classes were not initialized.")
                if oof_probabilities is None:
                    oof_probabilities = np.full((len(target), len(global_classes)), np.nan)
                for class_index, class_label in enumerate(fold_classes):
                    oof_probabilities[validation_indices, global_classes.index(class_label)] = (
                        fold_probabilities[:, class_index]
                    )
                aligned_probabilities = oof_probabilities[validation_indices]
                aligned_probabilities = np.clip(aligned_probabilities, 0.0, 1.0)
                aligned_probabilities /= aligned_probabilities.sum(axis=1, keepdims=True)
                oof_probabilities[validation_indices] = aligned_probabilities
                metrics = _classification_metrics(
                    validation_target,
                    predicted,
                    aligned_probabilities,
                    global_classes,
                    task_type,
                    positive_label,
                )
            predict_seconds = time.perf_counter() - predict_started
            oof_predictions[validation_indices] = predicted
            fold_assignments[validation_indices] = fold_number
            fold_scores.append(
                FoldScore(
                    fold=fold_number,
                    train_rows=len(train_indices),
                    validation_rows=len(validation_indices),
                    metrics=metrics,
                    fit_seconds=round(fit_seconds, 6),
                    predict_seconds=round(predict_seconds, 6),
                )
            )
            if fold_progress is not None:
                fold_progress(fold_number, metrics[primary_metric])
        summaries = _metric_summaries(fold_scores)
        primary = summaries[primary_metric]
        return _CandidateEvaluation(
            score=ModelScore(
                model_name=name,
                primary_metric=primary_metric,
                mean_score=primary.mean,
                score_std=primary.standard_deviation,
                fit_seconds=round(time.perf_counter() - started, 3),
                metrics=summaries,
                fold_scores=fold_scores,
                hyperparameters=parameters,
            ),
            oof_predictions=oof_predictions,
            oof_probabilities=oof_probabilities,
            fold_assignments=fold_assignments,
            classes=global_classes,
        )
    except (TournamentCancelled, TuningPruned):
        raise
    except Exception as exc:
        return _CandidateEvaluation(
            score=ModelScore(
                model_name=name,
                primary_metric=primary_metric,
                mean_score=float("nan"),
                score_std=float("nan"),
                fit_seconds=round(time.perf_counter() - started, 3),
                status="failed",
                error=str(exc)[:500],
                failure_stage=f"cross_validation_fold_{len(fold_scores) + 1}",
                fold_scores=fold_scores,
                metrics=_metric_summaries(fold_scores),
                hyperparameters=parameters,
            )
        )


def _threshold_analysis(
    actual: pd.Series,
    positive_probabilities: np.ndarray[Any, Any],
    positive_label: Any,
    display_positive_label: Any,
) -> ThresholdAnalysis:
    actual_binary = (actual.to_numpy() == positive_label).astype(int)
    points: list[ThresholdPoint] = []
    for threshold in np.linspace(0.1, 0.9, 17):
        predicted = (positive_probabilities >= threshold).astype(int)
        points.append(
            ThresholdPoint(
                threshold=round(float(threshold), 3),
                precision=float(precision_score(actual_binary, predicted, zero_division=0)),
                recall=float(recall_score(actual_binary, predicted, zero_division=0)),
                f1=float(f1_score(actual_binary, predicted, zero_division=0)),
            )
        )
    recommended = max(points, key=lambda point: (point.f1, -abs(point.threshold - 0.5)))
    return ThresholdAnalysis(
        positive_label=str(_python_value(display_positive_label)),
        recommended_threshold=recommended.threshold,
        recommendation_basis="Highest out-of-fold F1; ties prefer the threshold nearest 0.5.",
        points=points,
    )


def _calibration_summary(
    actual: pd.Series,
    positive_probabilities: np.ndarray[Any, Any],
    positive_label: Any,
    display_positive_label: Any,
) -> CalibrationSummary:
    actual_binary = (actual.to_numpy() == positive_label).astype(int)
    observed, predicted = calibration_curve(
        actual_binary, positive_probabilities, n_bins=10, strategy="uniform"
    )
    bin_indices = np.minimum((positive_probabilities * 10).astype(int), 9)
    expected_error = 0.0
    for bin_index in range(10):
        mask = bin_indices == bin_index
        if mask.any():
            expected_error += float(mask.mean()) * abs(
                float(actual_binary[mask].mean()) - float(positive_probabilities[mask].mean())
            )
    return CalibrationSummary(
        positive_label=str(_python_value(display_positive_label)),
        brier_score=float(brier_score_loss(actual_binary, positive_probabilities)),
        expected_calibration_error=expected_error,
        bins=[
            CalibrationBin(
                mean_predicted_probability=float(predicted_value),
                observed_positive_rate=float(observed_value),
            )
            for observed_value, predicted_value in zip(observed, predicted, strict=True)
        ],
    )


def _oof_records(
    target: pd.Series,
    evaluation: _CandidateEvaluation,
    positive_label: Any | None,
    label_lookup: dict[Any, Any],
) -> list[OutOfFoldPrediction]:
    if evaluation.oof_predictions is None or evaluation.fold_assignments is None:
        return []
    records: list[OutOfFoldPrediction] = []
    for position, (index, actual) in enumerate(target.items()):
        probabilities: dict[str, float] = {}
        positive_probability: float | None = None
        if evaluation.oof_probabilities is not None and evaluation.classes is not None:
            probabilities = {
                str(_python_value(label_lookup.get(label, label))): float(
                    evaluation.oof_probabilities[position, offset]
                )
                for offset, label in enumerate(evaluation.classes)
            }
            if positive_label is not None:
                positive_probability = probabilities[
                    str(_python_value(label_lookup.get(positive_label, positive_label)))
                ]
        records.append(
            OutOfFoldPrediction(
                row_index=str(index),
                fold=int(evaluation.fold_assignments[position]),
                actual=_python_value(label_lookup.get(actual, actual)),
                predicted=_python_value(
                    label_lookup.get(
                        evaluation.oof_predictions[position],
                        evaluation.oof_predictions[position],
                    )
                ),
                positive_probability=positive_probability,
                class_probabilities=probabilities,
            )
        )
    return records


def _save_artifact(artifact: dict[str, Any], artifact_path: Path) -> ArtifactManifest:
    if artifact_path.suffix.lower() != ".skops":
        raise ValueError("Winner artifact paths must use the .skops extension.")
    try:
        import skops.io as sio
    except ImportError as exc:
        raise RuntimeError("Install the 'ml' extra to save safe skops artifacts.") from exc
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    sio.dump(artifact, artifact_path)
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    return ArtifactManifest(
        path=str(artifact_path.resolve()),
        sha256=digest,
        size_bytes=artifact_path.stat().st_size,
        untrusted_types=sorted(sio.get_untrusted_types(file=artifact_path)),
    )


def run_supervised_tournament(
    df: pd.DataFrame,
    decision: TaskDecision,
    seed: int = 42,
    max_models: int = 5,
    forbidden_features: list[str] | None = None,
    forced_features: list[str] | None = None,
    acknowledged_risks: list[str] | None = None,
    compute_budget_seconds: int = 600,
    winner_artifact_path: Path | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
    tuning_enabled: bool = False,
    tuning_trials: int = 10,
    tuning_timeout_seconds: int = 120,
    experiment_tuning_trial_limit: int = 10,
    experiment_tuning_time_limit_seconds: int = 120,
    user_tuning_trial_limit: int = 20,
    user_tuning_time_limit_seconds: int = 180,
    tuning_max_candidates: int = 2,
    explanations_enabled: bool = False,
    explanation_max_sample_rows: int = 200,
    explanation_background_rows: int = 50,
    explanation_local_rows: int = 5,
    explanation_max_features: int = 15,
    explanation_plot_sample_rows: int = 500,
    explanation_learning_curve_rows: int = 2_000,
) -> ExperimentResult:
    if not decision.target_column:
        raise ValueError("A target column is required for supervised model training.")
    if decision.task_type not in {
        TaskType.BINARY_CLASSIFICATION,
        TaskType.MULTICLASS_CLASSIFICATION,
        TaskType.REGRESSION,
    }:
        raise ValueError(f"The supervised tournament does not train {decision.task_type} tasks.")
    if max_models < 1:
        raise ValueError("At least one candidate model is required.")
    if compute_budget_seconds < 1:
        raise ValueError("The compute budget must be at least one second.")
    if not isinstance(tuning_enabled, bool):
        raise ValueError("tuning_enabled must be true or false.")
    if not isinstance(explanations_enabled, bool):
        raise ValueError("explanations_enabled must be true or false.")
    explanation_limits = {
        "explanation_max_sample_rows": explanation_max_sample_rows,
        "explanation_background_rows": explanation_background_rows,
        "explanation_local_rows": explanation_local_rows,
        "explanation_max_features": explanation_max_features,
        "explanation_plot_sample_rows": explanation_plot_sample_rows,
        "explanation_learning_curve_rows": explanation_learning_curve_rows,
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in explanation_limits.values()
    ):
        raise ValueError("Every explanation limit must be a positive integer.")

    modelling_df = df.dropna(subset=[decision.target_column]).copy()
    features = modelling_df.drop(columns=[decision.target_column])
    original_target = modelling_df[decision.target_column]
    quality_report = assess_data_quality(
        modelling_df,
        target_column=decision.target_column,
        forbidden_features=forbidden_features,
        forced_features=forced_features,
        acknowledged_risks=acknowledged_risks,
    )
    if not quality_report.can_train:
        details = "; ".join(item.message for item in quality_report.blocking_errors)
        raise ValueError(f"Data-quality guardian blocked training: {details}")
    preprocessing = build_preprocessor(
        features,
        excluded_columns=quality_report.suggested_exclusions,
        force_include=forced_features,
    )
    if not preprocessing.numeric_columns and not preprocessing.categorical_columns:
        raise ValueError("No usable feature columns remain after safety exclusions.")
    usable_features = features.drop(columns=preprocessing.excluded_columns, errors="ignore")

    positive_label: Any | None = None
    display_positive_label: Any | None = None
    label_lookup: dict[Any, Any] = {}
    if decision.task_type == TaskType.REGRESSION:
        target = original_target
        primary_metric = "root_mean_squared_error"
        splitter = KFold(n_splits=5, shuffle=True, random_state=seed)
        factories = _regression_models(seed)
        validation_strategy = "5-fold shuffled KFold with fold-fitted preprocessing"
    else:
        counts = original_target.value_counts()
        if len(counts) < 2 or int(counts.min()) < 2:
            raise ValueError("Classification requires at least two examples in every class.")
        label_encoder = LabelEncoder()
        encoded_values = label_encoder.fit_transform(original_target)
        target = pd.Series(encoded_values, index=original_target.index, name=original_target.name)
        label_lookup = {
            int(index): _python_value(label) for index, label in enumerate(label_encoder.classes_)
        }
        split_count = min(5, int(counts.min()))
        splitter = StratifiedKFold(n_splits=split_count, shuffle=True, random_state=seed)
        factories = _classification_models(seed)
        validation_strategy = (
            f"{split_count}-fold shuffled StratifiedKFold with fold-fitted preprocessing"
        )
        if decision.task_type == TaskType.BINARY_CLASSIFICATION:
            primary_metric = "average_precision"
            display_positive_label = counts.idxmin()
            positive_label = int(label_encoder.transform([display_positive_label])[0])
        else:
            primary_metric = "f1_macro"

    planned = plan_candidates(
        usable_features,
        target,
        decision.task_type,
        factories,
        max_models=max_models,
        compute_budget_seconds=compute_budget_seconds,
    )
    splits = list(splitter.split(features, target))
    tournament_started = time.perf_counter()
    evaluations: list[_CandidateEvaluation] = []
    candidate_count = len(planned.factories)
    for candidate_index, (name, factory) in enumerate(planned.factories.items()):
        if cancellation_check is not None and cancellation_check():
            raise TournamentCancelled("Experiment cancellation was requested.")
        if progress_callback is not None:
            progress_callback(
                25 + int((candidate_index / max(candidate_count, 1)) * 55),
                f"Evaluating {name}",
            )
        if time.perf_counter() - tournament_started >= compute_budget_seconds:
            evaluations.append(
                _CandidateEvaluation(
                    score=ModelScore(
                        model_name=name,
                        primary_metric=primary_metric,
                        mean_score=float("nan"),
                        score_std=float("nan"),
                        fit_seconds=0,
                        status="failed",
                        error="The tournament compute budget was exhausted before evaluation.",
                        failure_stage="resource_budget",
                    )
                )
            )
            continue
        evaluations.append(
            _evaluate_candidate(
                name,
                factory,
                features,
                target,
                preprocessing,
                splits,
                decision.task_type,
                primary_metric,
                positive_label,
            )
        )

    reverse = decision.task_type != TaskType.REGRESSION
    successful = [item for item in evaluations if item.score.status == "completed"]
    successful.sort(key=lambda item: item.score.mean_score, reverse=reverse)
    failed = [item for item in evaluations if item.score.status != "completed"]
    ordered = [*successful, *failed]

    tuning_summary = TuningSummary(
        enabled=False,
        seed=seed,
        reason_disabled="Tuning was not requested for this experiment.",
    )
    final_factories = dict(planned.factories)
    if tuning_enabled:
        elapsed = time.perf_counter() - tournament_started
        remaining_seconds = int(compute_budget_seconds - elapsed)
        if remaining_seconds < 1:
            tuning_summary = TuningSummary(
                enabled=True,
                seed=seed,
                reason_disabled="The untuned tournament exhausted the experiment compute budget.",
            )
        else:
            budget = resolve_tuning_budget(
                rows=len(features),
                requested_trials=tuning_trials,
                requested_seconds=tuning_timeout_seconds,
                experiment_trial_limit=experiment_tuning_trial_limit,
                experiment_time_limit_seconds=min(
                    experiment_tuning_time_limit_seconds, remaining_seconds
                ),
                user_trial_limit=user_tuning_trial_limit,
                user_time_limit_seconds=user_tuning_time_limit_seconds,
                max_candidates=tuning_max_candidates,
            )
            if progress_callback is not None:
                progress_callback(80, "Running bounded Optuna tuning")

            def tune_evaluate(
                name: str,
                factory: Callable[[], BaseEstimator],
                fold_progress: Callable[[int, float], None],
            ) -> _CandidateEvaluation:
                return _evaluate_candidate(
                    name,
                    factory,
                    features,
                    target,
                    preprocessing,
                    splits,
                    decision.task_type,
                    primary_metric,
                    positive_label,
                    fold_progress,
                )

            tuning_outcome = run_optuna_tuning(
                ordered_evaluations=ordered,
                factories=planned.factories,
                evaluate=tune_evaluate,
                direction="minimize" if decision.task_type == TaskType.REGRESSION else "maximize",
                seed=seed,
                budget=budget,
                cancellation_check=cancellation_check,
            )
            tuning_summary = tuning_outcome.summary
            evaluations.extend(tuning_outcome.evaluations)
            final_factories.update(tuning_outcome.factories)
            successful = [item for item in evaluations if item.score.status == "completed"]
            successful.sort(key=lambda item: item.score.mean_score, reverse=reverse)
            failed = [item for item in evaluations if item.score.status != "completed"]
            ordered = [*successful, *failed]

    winner_evaluation: _CandidateEvaluation | None = None
    winner_pipeline: Pipeline | None = None
    for evaluation in successful:
        if cancellation_check is not None and cancellation_check():
            raise TournamentCancelled("Experiment cancellation was requested.")
        factory = final_factories[evaluation.score.model_name]
        pipeline = Pipeline(
            [("preprocessor", clone(preprocessing.transformer)), ("model", factory())]
        )
        try:
            pipeline.fit(features, target)
            winner_evaluation = evaluation
            winner_pipeline = pipeline
            break
        except Exception as exc:
            evaluation.score.status = "failed"
            evaluation.score.failure_stage = "final_fit"
            evaluation.score.error = str(exc)[:500]
    if winner_evaluation is None or winner_pipeline is None:
        return ExperimentResult(
            task=decision,
            primary_metric=primary_metric,
            leaderboard=[item.score for item in ordered],
            winner=None,
            warnings=["Every candidate failed during validation or final fitting."],
            quality_report=quality_report,
            validation_strategy=validation_strategy,
            candidate_plan=planned.evidence,
            tuning=tuning_summary,
            random_seed=seed,
            software_versions=_software_versions(),
        )

    if progress_callback is not None:
        progress_callback(88, "Final model fitted")

    successful_after_fit = [item for item in ordered if item.score.status == "completed"]
    successful_after_fit.sort(key=lambda item: item.score.mean_score, reverse=reverse)
    ordered = [
        *successful_after_fit,
        *[item for item in ordered if item.score.status != "completed"],
    ]

    explanation_evidence: ExplanationEvidence | None = None
    error_analysis: ErrorAnalysisEvidence | None = None
    if explanations_enabled:
        if winner_evaluation.oof_predictions is None or winner_evaluation.fold_assignments is None:
            raise RuntimeError("Winner out-of-fold evidence is unavailable for Stage 11 analysis.")
        if progress_callback is not None:
            progress_callback(89, "Building explanation and error evidence")
        try:
            explanation_evidence, error_analysis = build_explanation_and_error_analysis(
                winner_pipeline,
                features,
                target,
                winner_evaluation.oof_predictions,
                winner_evaluation.oof_probabilities,
                winner_evaluation.classes,
                decision.task_type,
                positive_label,
                label_lookup,
                winner_evaluation.score.model_name,
                seed=seed,
                max_sample_rows=explanation_max_sample_rows,
                background_rows=explanation_background_rows,
                local_rows=explanation_local_rows,
                max_features=explanation_max_features,
                plot_sample_rows=explanation_plot_sample_rows,
                learning_curve_rows=explanation_learning_curve_rows,
                cancellation_check=cancellation_check,
            )
        except ExplanationCancelled as exc:
            raise TournamentCancelled(str(exc)) from exc

    artifact_bundle = {
        "pipeline": winner_pipeline,
        "task_type": decision.task_type.value,
        "target_column": decision.target_column,
        "target_classes": [label_lookup[key] for key in sorted(label_lookup)],
        "positive_label": _python_value(display_positive_label),
        "feature_columns": [str(column) for column in features.columns],
        "excluded_columns": preprocessing.excluded_columns,
        "random_seed": seed,
        "tuning": tuning_summary.model_dump(mode="json"),
        "explanations": (
            explanation_evidence.model_dump(mode="json") if explanation_evidence else None
        ),
        "error_analysis": error_analysis.model_dump(mode="json") if error_analysis else None,
        "software_versions": _software_versions(),
    }
    winner_artifact = (
        _save_artifact(artifact_bundle, winner_artifact_path)
        if winner_artifact_path is not None
        else None
    )
    oof_records = _oof_records(target, winner_evaluation, positive_label, label_lookup)
    calibration: CalibrationSummary | None = None
    thresholds: ThresholdAnalysis | None = None
    if (
        decision.task_type == TaskType.BINARY_CLASSIFICATION
        and winner_evaluation.oof_probabilities is not None
        and winner_evaluation.classes is not None
        and positive_label is not None
    ):
        positive_probabilities = winner_evaluation.oof_probabilities[
            :, winner_evaluation.classes.index(positive_label)
        ]
        calibration = _calibration_summary(
            target,
            positive_probabilities,
            positive_label,
            display_positive_label,
        )
        thresholds = _threshold_analysis(
            target,
            positive_probabilities,
            positive_label,
            display_positive_label,
        )

    warnings: list[str] = []
    if positive_label is not None:
        warnings.append(
            f"Binary metrics treat '{_python_value(display_positive_label)}' as the positive class."
        )
    if preprocessing.excluded_columns:
        warnings.append(
            "Excluded safety-risk columns: " + ", ".join(preprocessing.excluded_columns)
        )
    if tuning_summary.enabled:
        warnings.append(
            "Tuned candidates were selected on the same cross-validation design used for the "
            "untuned comparison; preserve an external holdout for final generalization claims."
        )
    if explanation_evidence is not None:
        warnings.extend(explanation_evidence.warnings)
    if error_analysis is not None:
        warnings.extend(error_analysis.warnings)
    return ExperimentResult(
        task=decision,
        primary_metric=primary_metric,
        leaderboard=[item.score for item in ordered],
        winner=winner_evaluation.score.model_name,
        warnings=warnings,
        quality_report=quality_report,
        validation_strategy=validation_strategy,
        candidate_plan=planned.evidence,
        tuning=tuning_summary,
        out_of_fold_predictions=oof_records,
        calibration=calibration,
        threshold_analysis=thresholds,
        explanations=explanation_evidence,
        error_analysis=error_analysis,
        winner_artifact=winner_artifact,
        fitted_winner=True,
        random_seed=seed,
        software_versions=_software_versions(),
    )

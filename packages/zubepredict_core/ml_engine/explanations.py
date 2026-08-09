from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import clone
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import confusion_matrix, precision_recall_curve, roc_curve
from sklearn.model_selection import KFold, StratifiedKFold, learning_curve
from sklearn.pipeline import Pipeline

from zubepredict_core.shared.schemas import (
    DiagnosticPlot,
    ErrorAnalysisEvidence,
    ExplanationEvidence,
    FeatureContribution,
    FeatureImportance,
    LocalExplanation,
    PlotSeries,
    SegmentError,
    TaskType,
)

PROTECTED_NAME_PARTS = {
    "age",
    "disability",
    "ethnicity",
    "gender",
    "nationality",
    "pregnancy",
    "race",
    "religion",
    "sex",
}


class ExplanationCancelled(RuntimeError):
    """Raised at a safe explanation boundary after cancellation is requested."""


def _dense(values: Any) -> np.ndarray[Any, Any]:
    if sparse.issparse(values):
        return np.asarray(values.toarray(), dtype=float)
    return np.asarray(values, dtype=float)


def _sample_positions(rows: int, limit: int, seed: int) -> list[int]:
    if rows <= limit:
        return list(range(rows))
    generator = np.random.default_rng(seed)
    return sorted(int(value) for value in generator.choice(rows, size=limit, replace=False))


def _display(value: Any, label_lookup: dict[Any, Any]) -> Any:
    if hasattr(value, "item"):
        value = value.item()
    return label_lookup.get(value, value)


def _worst_positions(
    target: pd.Series,
    predictions: np.ndarray[Any, Any],
    probabilities: np.ndarray[Any, Any] | None,
    task_type: TaskType,
    limit: int,
) -> list[int]:
    if task_type == TaskType.REGRESSION:
        errors = np.abs(target.to_numpy(dtype=float) - predictions.astype(float))
        return [int(value) for value in np.argsort(-errors)[:limit]]
    wrong = np.flatnonzero(predictions != target.to_numpy())
    if probabilities is None:
        ordered = list(wrong)
    else:
        confidence = probabilities.max(axis=1)
        ordered = sorted((int(value) for value in wrong), key=lambda value: confidence[value])
        ordered.extend(
            int(value) for value in np.argsort(confidence) if int(value) not in set(ordered)
        )
    return ordered[:limit]


def _feature_names(pipeline: Pipeline) -> list[str]:
    preprocessor = pipeline.named_steps["preprocessor"]
    try:
        names = [str(value) for value in preprocessor.get_feature_names_out()]
    except Exception:
        transformed_width = int(preprocessor.transform(pd.DataFrame()).shape[1])
        names = [f"feature_{index}" for index in range(transformed_width)]
    return [name.replace("numeric__", "").replace("categorical__", "") for name in names]


def _shap_evidence(
    pipeline: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
    predictions: np.ndarray[Any, Any],
    probabilities: np.ndarray[Any, Any] | None,
    task_type: TaskType,
    label_lookup: dict[Any, Any],
    model_name: str,
    *,
    seed: int,
    max_sample_rows: int,
    background_rows: int,
    local_rows: int,
    max_features: int,
    check_cancel: Callable[[], None],
) -> ExplanationEvidence:
    import shap

    check_cancel()
    model = pipeline.named_steps["model"]
    preprocessor = pipeline.named_steps["preprocessor"]
    sampled_positions = _sample_positions(len(features), max_sample_rows, seed)
    local_positions = _worst_positions(
        target, predictions, probabilities, task_type, min(local_rows, max_sample_rows)
    )
    explained_positions = list(dict.fromkeys([*local_positions, *sampled_positions]))[
        :max_sample_rows
    ]
    background_positions = _sample_positions(len(features), background_rows, seed + 1)
    background_matrix = _dense(preprocessor.transform(features.iloc[background_positions]))
    explained_matrix = _dense(preprocessor.transform(features.iloc[explained_positions]))
    feature_names = _feature_names(pipeline)

    if isinstance(model, (DummyClassifier, DummyRegressor)):
        effects = [
            FeatureImportance(feature=name, importance=0.0) for name in feature_names[:max_features]
        ]
        local = [
            LocalExplanation(
                row_index=str(features.index[position]),
                actual=_display(target.iloc[position], label_lookup),
                predicted=_display(predictions[position], label_lookup),
                explained_output=(
                    "prediction"
                    if task_type == TaskType.REGRESSION
                    else str(_display(predictions[position], label_lookup))
                ),
                contributions=[],
                caveat=(
                    "The constant baseline does not use feature values, so all effects are zero."
                ),
            )
            for position in local_positions
        ]
        return ExplanationEvidence(
            method="constant_baseline",
            model_name=model_name,
            sampled_rows=len(explained_positions),
            background_rows=len(background_positions),
            encoded_feature_count=len(feature_names),
            global_importance=effects,
            local_explanations=local,
            warnings=["The selected baseline is feature-independent."],
            random_seed=seed,
        )

    output_names = None
    if task_type != TaskType.REGRESSION and hasattr(model, "classes_"):
        output_names = [str(_display(value, label_lookup)) for value in model.classes_]
    explainer = shap.Explainer(
        model,
        background_matrix,
        feature_names=feature_names,
        output_names=output_names,
        seed=seed,
    )
    explanation = explainer(explained_matrix)
    values = np.asarray(explanation.values, dtype=float)
    if values.ndim == 1:
        values = values.reshape(1, -1)
    if values.ndim == 2:
        global_values = np.mean(np.abs(values), axis=0)
    elif values.ndim == 3:
        global_values = np.mean(np.abs(values), axis=(0, 2))
    else:
        raise ValueError(f"Unsupported SHAP value shape: {values.shape}")
    top_indices = np.argsort(-global_values)[:max_features]
    global_importance = [
        FeatureImportance(feature=feature_names[index], importance=float(global_values[index]))
        for index in top_indices
    ]

    position_lookup = {position: offset for offset, position in enumerate(explained_positions)}
    local_explanations: list[LocalExplanation] = []
    classes = list(getattr(model, "classes_", []))
    for position in local_positions:
        offset = position_lookup[position]
        if values.ndim == 2:
            local_values = values[offset]
            explained_output = (
                "prediction"
                if task_type == TaskType.REGRESSION
                else str(_display(predictions[position], label_lookup))
            )
        else:
            predicted_class = predictions[position]
            output_index = classes.index(predicted_class) if predicted_class in classes else 0
            local_values = values[offset, :, output_index]
            explained_output = str(_display(predicted_class, label_lookup))
        local_indices = np.argsort(-np.abs(local_values))[:max_features]
        local_explanations.append(
            LocalExplanation(
                row_index=str(features.index[position]),
                actual=_display(target.iloc[position], label_lookup),
                predicted=_display(predictions[position], label_lookup),
                explained_output=explained_output,
                contributions=[
                    FeatureContribution(
                        feature=feature_names[index], contribution=float(local_values[index])
                    )
                    for index in local_indices
                ],
                caveat=(
                    "Feature attributions describe this fitted model's output under the SHAP "
                    "background distribution; they are not causal effects."
                ),
            )
        )
    check_cancel()
    return ExplanationEvidence(
        method=f"shap.{type(explainer).__name__}",
        model_name=model_name,
        sampled_rows=len(explained_positions),
        background_rows=len(background_positions),
        encoded_feature_count=len(feature_names),
        global_importance=global_importance,
        local_explanations=local_explanations,
        warnings=[
            "SHAP values explain model output under the sampled background distribution and do "
            "not establish causality."
        ],
        random_seed=seed,
    )


def _fallback_evidence(
    pipeline: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
    predictions: np.ndarray[Any, Any],
    probabilities: np.ndarray[Any, Any] | None,
    task_type: TaskType,
    label_lookup: dict[Any, Any],
    model_name: str,
    *,
    seed: int,
    max_sample_rows: int,
    local_rows: int,
    max_features: int,
    warning: str,
    check_cancel: Callable[[], None],
) -> ExplanationEvidence:
    check_cancel()
    positions = _sample_positions(len(features), max_sample_rows, seed)
    scoring = {
        TaskType.REGRESSION: "neg_root_mean_squared_error",
        TaskType.BINARY_CLASSIFICATION: "average_precision",
        TaskType.MULTICLASS_CLASSIFICATION: "f1_macro",
    }[task_type]
    result = permutation_importance(
        pipeline,
        features.iloc[positions],
        target.iloc[positions],
        scoring=scoring,
        n_repeats=3,
        random_state=seed,
        n_jobs=1,
    )
    names = [str(value) for value in features.columns]
    top_indices = np.argsort(-np.abs(result.importances_mean))[:max_features]
    global_importance = [
        FeatureImportance(
            feature=names[index],
            importance=float(result.importances_mean[index]),
            standard_deviation=float(result.importances_std[index]),
        )
        for index in top_indices
    ]

    reference: dict[str, Any] = {}
    for name in names:
        series = features[name]
        if pd.api.types.is_numeric_dtype(series):
            reference[name] = float(series.median())
        else:
            modes = series.mode(dropna=True)
            reference[name] = modes.iloc[0] if not modes.empty else None
    local_positions = _worst_positions(target, predictions, probabilities, task_type, local_rows)
    local_explanations: list[LocalExplanation] = []
    for position in local_positions:
        row = features.iloc[[position]].copy()
        original_prediction = pipeline.predict(row)[0]
        if task_type == TaskType.REGRESSION:
            original_output = float(original_prediction)
            explained_output = "prediction"
            class_index = None
        else:
            classes = list(pipeline.classes_)
            class_index = classes.index(original_prediction)
            original_output = float(pipeline.predict_proba(row)[0, class_index])
            explained_output = str(_display(original_prediction, label_lookup))
        contributions: list[FeatureContribution] = []
        for index in top_indices:
            name = names[index]
            counterfactual = row.copy()
            counterfactual[name] = reference[name]
            if task_type == TaskType.REGRESSION:
                counterfactual_output = float(pipeline.predict(counterfactual)[0])
            else:
                assert class_index is not None
                counterfactual_output = float(
                    pipeline.predict_proba(counterfactual)[0, class_index]
                )
            contributions.append(
                FeatureContribution(
                    feature=name,
                    contribution=original_output - counterfactual_output,
                )
            )
        local_explanations.append(
            LocalExplanation(
                row_index=str(features.index[position]),
                actual=_display(target.iloc[position], label_lookup),
                predicted=_display(predictions[position], label_lookup),
                explained_output=explained_output,
                contributions=contributions,
                caveat=(
                    "Each value is the model-output change after replacing one feature with a "
                    "reference value. Features may be dependent, so this is not causal."
                ),
            )
        )
    check_cancel()
    return ExplanationEvidence(
        method="permutation_importance_and_local_reference_perturbation",
        model_name=model_name,
        sampled_rows=len(positions),
        background_rows=0,
        encoded_feature_count=len(_feature_names(pipeline)),
        global_importance=global_importance,
        local_explanations=local_explanations,
        warnings=[warning, "Permutation importance on training rows is descriptive, not causal."],
        random_seed=seed,
    )


def _learning_plot(
    pipeline: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
    task_type: TaskType,
    seed: int,
    row_limit: int,
    check_cancel: Callable[[], None],
) -> DiagnosticPlot | None:
    positions = _sample_positions(len(features), row_limit, seed + 7)
    sampled_features = features.iloc[positions]
    sampled_target = target.iloc[positions]
    if task_type == TaskType.REGRESSION:
        splits = min(3, len(sampled_target) // 10)
        if splits < 2:
            return None
        cv: Any = KFold(n_splits=splits, shuffle=True, random_state=seed)
        scoring = "neg_root_mean_squared_error"
    else:
        counts = sampled_target.value_counts()
        splits = min(3, int(counts.min())) if not counts.empty else 0
        if splits < 2:
            return None
        cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=seed)
        scoring = "average_precision" if task_type == TaskType.BINARY_CLASSIFICATION else "f1_macro"
    check_cancel()
    sizes, train_scores, validation_scores = learning_curve(
        clone(pipeline),
        sampled_features,
        sampled_target,
        train_sizes=np.asarray([0.35, 0.65, 1.0]),
        cv=cv,
        scoring=scoring,
        shuffle=True,
        random_state=seed,
        n_jobs=1,
        error_score=np.nan,
    )
    check_cancel()
    if task_type == TaskType.REGRESSION:
        train_values = -np.nanmean(train_scores, axis=1)
        validation_values = -np.nanmean(validation_scores, axis=1)
        y_label = "RMSE (lower is better)"
    else:
        train_values = np.nanmean(train_scores, axis=1)
        validation_values = np.nanmean(validation_scores, axis=1)
        y_label = "Primary metric (higher is better)"
    return DiagnosticPlot(
        plot_id="learning_curve",
        kind="learning_curve",
        title="Learning curve",
        x_label="Training rows",
        y_label=y_label,
        series=[
            PlotSeries(name="training", x=sizes.astype(int).tolist(), y=train_values.tolist()),
            PlotSeries(
                name="cross-validation",
                x=sizes.astype(int).tolist(),
                y=validation_values.tolist(),
            ),
        ],
        caveat=(
            "Scores summarize resampled model behavior and do not guarantee performance on a "
            "different population."
        ),
    )


def _diagnostic_plots(
    pipeline: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
    predictions: np.ndarray[Any, Any],
    probabilities: np.ndarray[Any, Any] | None,
    classes: list[Any] | None,
    task_type: TaskType,
    positive_label: Any | None,
    label_lookup: dict[Any, Any],
    *,
    seed: int,
    plot_sample_rows: int,
    learning_curve_rows: int,
    check_cancel: Callable[[], None],
) -> tuple[list[DiagnosticPlot], list[str]]:
    check_cancel()
    plots: list[DiagnosticPlot] = []
    warnings: list[str] = []
    caveat = "Built from out-of-fold predictions; visual patterns are descriptive, not causal."
    if task_type == TaskType.REGRESSION:
        positions = _sample_positions(len(target), plot_sample_rows, seed + 5)
        actual = target.to_numpy(dtype=float)[positions]
        predicted = predictions.astype(float)[positions]
        residuals = actual - predicted
        plots.extend(
            [
                DiagnosticPlot(
                    plot_id="residuals",
                    kind="residuals",
                    title="Out-of-fold residuals",
                    x_label="Predicted value",
                    y_label="Actual - predicted",
                    series=[PlotSeries(name="rows", x=predicted.tolist(), y=residuals.tolist())],
                    caveat=caveat,
                ),
                DiagnosticPlot(
                    plot_id="actual_vs_predicted",
                    kind="actual_vs_predicted",
                    title="Actual versus out-of-fold predicted",
                    x_label="Actual value",
                    y_label="Predicted value",
                    series=[PlotSeries(name="rows", x=actual.tolist(), y=predicted.tolist())],
                    caveat=caveat,
                ),
            ]
        )
    else:
        if classes is None:
            return plots, ["Classification diagnostic classes were unavailable."]
        classification_predictions = np.asarray(predictions.tolist())
        matrix = confusion_matrix(target, classification_predictions, labels=classes)
        labels = [str(_display(value, label_lookup)) for value in classes]
        plots.append(
            DiagnosticPlot(
                plot_id="confusion_matrix",
                kind="confusion_matrix",
                title="Out-of-fold confusion matrix",
                x_label="Predicted label",
                y_label="Actual label",
                matrix=matrix.astype(int).tolist(),
                labels=labels,
                caveat=caveat,
            )
        )
        if (
            task_type == TaskType.BINARY_CLASSIFICATION
            and probabilities is not None
            and positive_label in classes
        ):
            positive_index = classes.index(positive_label)
            scores = probabilities[:, positive_index]
            actual_binary = (target.to_numpy() == positive_label).astype(int)
            false_positive, true_positive, _ = roc_curve(actual_binary, scores)
            precision, recall, _ = precision_recall_curve(actual_binary, scores)
            observed, predicted_probability = calibration_curve(
                actual_binary, scores, n_bins=10, strategy="uniform"
            )
            plots.extend(
                [
                    DiagnosticPlot(
                        plot_id="roc_curve",
                        kind="roc_curve",
                        title="Out-of-fold ROC curve",
                        x_label="False-positive rate",
                        y_label="True-positive rate",
                        series=[
                            PlotSeries(
                                name=str(_display(positive_label, label_lookup)),
                                x=false_positive.tolist(),
                                y=true_positive.tolist(),
                            )
                        ],
                        caveat=caveat,
                    ),
                    DiagnosticPlot(
                        plot_id="precision_recall_curve",
                        kind="precision_recall_curve",
                        title="Out-of-fold precision-recall curve",
                        x_label="Recall",
                        y_label="Precision",
                        series=[
                            PlotSeries(
                                name=str(_display(positive_label, label_lookup)),
                                x=recall.tolist(),
                                y=precision.tolist(),
                            )
                        ],
                        caveat=caveat,
                    ),
                    DiagnosticPlot(
                        plot_id="calibration_curve",
                        kind="calibration_curve",
                        title="Out-of-fold calibration curve",
                        x_label="Mean predicted probability",
                        y_label="Observed positive rate",
                        series=[
                            PlotSeries(
                                name=str(_display(positive_label, label_lookup)),
                                x=predicted_probability.tolist(),
                                y=observed.tolist(),
                            )
                        ],
                        caveat=caveat,
                    ),
                ]
            )
    try:
        learning = _learning_plot(
            pipeline,
            features,
            target,
            task_type,
            seed,
            learning_curve_rows,
            check_cancel,
        )
        if learning is not None:
            plots.append(learning)
        else:
            warnings.append("There were too few rows or class examples for a learning curve.")
    except ExplanationCancelled:
        raise
    except Exception as exc:
        warnings.append(f"Learning-curve generation failed safely: {str(exc)[:300]}")
    return plots, warnings


def _segment_errors(
    features: pd.DataFrame,
    target: pd.Series,
    predictions: np.ndarray[Any, Any],
    task_type: TaskType,
) -> tuple[list[SegmentError], list[str]]:
    safe_columns: list[str] = []
    skipped: list[str] = []
    for column in features.columns:
        name = str(column)
        lowered = name.lower()
        tokens = set(re.split(r"[^a-z0-9]+", lowered))
        if lowered in PROTECTED_NAME_PARTS or PROTECTED_NAME_PARTS.intersection(tokens):
            skipped.append(name)
            continue
        series = features[column]
        unique = int(series.nunique(dropna=True))
        if (pd.api.types.is_numeric_dtype(series) and unique >= 4) or 2 <= unique <= 10:
            safe_columns.append(name)
    minimum_rows = max(5, math.ceil(len(features) * 0.02))
    actual = target.to_numpy()
    if task_type == TaskType.REGRESSION:
        row_errors = np.abs(actual.astype(float) - predictions.astype(float))
        metric_name: Literal["error_rate", "mean_absolute_error"] = "mean_absolute_error"
    else:
        row_errors = (actual != predictions).astype(float)
        metric_name = "error_rate"
    overall = float(np.mean(row_errors))
    segments: list[SegmentError] = []
    for name in safe_columns[:3]:
        series = features[name].reset_index(drop=True)
        if pd.api.types.is_numeric_dtype(series) and series.nunique(dropna=True) > 10:
            groups = pd.qcut(series, q=min(4, int(series.nunique())), duplicates="drop").astype(str)
        else:
            groups = series.fillna("<missing>").astype(str)
        for segment, indexes in groups.groupby(groups, sort=True).groups.items():
            positions = np.asarray(list(indexes), dtype=int)
            if len(positions) < minimum_rows:
                continue
            value = float(np.mean(row_errors[positions]))
            segments.append(
                SegmentError(
                    feature=name,
                    segment=str(segment),
                    rows=len(positions),
                    metric_name=metric_name,
                    metric_value=value,
                    overall_metric_value=overall,
                    difference_from_overall=value - overall,
                    caveat=(
                        "This is a descriptive association in out-of-fold errors. It does not "
                        "show that the segment feature causes the difference and is not causal."
                    ),
                )
            )
    segments.sort(key=lambda item: item.difference_from_overall, reverse=True)
    return segments, skipped


def build_explanation_and_error_analysis(
    pipeline: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
    predictions: np.ndarray[Any, Any],
    probabilities: np.ndarray[Any, Any] | None,
    classes: list[Any] | None,
    task_type: TaskType,
    positive_label: Any | None,
    label_lookup: dict[Any, Any],
    model_name: str,
    *,
    seed: int,
    max_sample_rows: int,
    background_rows: int,
    local_rows: int,
    max_features: int,
    plot_sample_rows: int,
    learning_curve_rows: int,
    cancellation_check: Callable[[], bool] | None = None,
) -> tuple[ExplanationEvidence, ErrorAnalysisEvidence]:
    def check_cancel() -> None:
        if cancellation_check is not None and cancellation_check():
            raise ExplanationCancelled(
                "Experiment cancellation was requested during explanation analysis."
            )

    try:
        explanations = _shap_evidence(
            pipeline,
            features,
            target,
            predictions,
            probabilities,
            task_type,
            label_lookup,
            model_name,
            seed=seed,
            max_sample_rows=max_sample_rows,
            background_rows=background_rows,
            local_rows=local_rows,
            max_features=max_features,
            check_cancel=check_cancel,
        )
    except ExplanationCancelled:
        raise
    except Exception as exc:
        explanations = _fallback_evidence(
            pipeline,
            features,
            target,
            predictions,
            probabilities,
            task_type,
            label_lookup,
            model_name,
            seed=seed,
            max_sample_rows=max_sample_rows,
            local_rows=local_rows,
            max_features=max_features,
            warning=(
                "SHAP was unavailable or incompatible; deterministic fallback used: "
                f"{str(exc)[:300]}"
            ),
            check_cancel=check_cancel,
        )
    plots, plot_warnings = _diagnostic_plots(
        pipeline,
        features,
        target,
        predictions,
        probabilities,
        classes,
        task_type,
        positive_label,
        label_lookup,
        seed=seed,
        plot_sample_rows=plot_sample_rows,
        learning_curve_rows=learning_curve_rows,
        check_cancel=check_cancel,
    )
    segments, skipped = _segment_errors(features, target, predictions, task_type)
    return explanations, ErrorAnalysisEvidence(
        plots=plots,
        segments=segments,
        protected_columns_skipped=skipped,
        warnings=plot_warnings
        + [
            "Segment comparisons are descriptive and must not be interpreted as causal or as a "
            "fairness assessment."
        ],
    )

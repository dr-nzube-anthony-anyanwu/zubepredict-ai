from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from zubepredict_core.shared.schemas import (
    DecisionEvidence,
    TargetCandidate,
    TaskDecision,
    TaskSuggestion,
    TaskType,
)

FORECAST_WORDS = ("forecast", "future", "time series", "predict over time")
ANOMALY_WORDS = ("anomaly", "anomalies", "unusual", "outlier", "outliers")
CLUSTER_WORDS = ("cluster", "clusters", "segment", "segments", "group similar")
SUPERVISED_WORDS = ("predict", "classify", "estimate", "target", "outcome")
GENERIC_TARGET_NAMES = {
    "target",
    "label",
    "outcome",
    "response",
    "class",
    "status",
}
SEMANTIC_TARGET_NAMES = {
    "readmitted",
    "diagnosis",
    "default",
    "churn",
    "fraud",
    "price",
    "cost",
    "sales",
    "revenue",
    "survived",
    "demand",
    "amount",
    "score",
}
TIME_NAME_PARTS = {"date", "time", "timestamp", "datetime", "month", "year", "week"}


@dataclass(frozen=True)
class _CandidateAnalysis:
    candidate: TargetCandidate
    missing_ratio: float
    unique_count: int


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _objective_mentions_column(objective: str, column: str) -> bool:
    normalized_column = _normalized(column)
    return bool(normalized_column and re.search(rf"\b{re.escape(normalized_column)}\b", objective))


def _is_identifier(column: str, series: pd.Series) -> bool:
    normalized = _normalized(column)
    name_tokens = set(normalized.split())
    name_hint = normalized == "id" or "id" in name_tokens or normalized.endswith(" identifier")
    non_null = series.dropna()
    unique_ratio = non_null.nunique() / max(len(non_null), 1)
    generated_text_key = (
        not is_numeric_dtype(non_null) and len(non_null) >= 20 and unique_ratio > 0.98
    )
    return bool(name_hint or generated_text_key)


def _analyze_candidate(
    column: str,
    series: pd.Series,
    objective: str,
    *,
    explicit: bool = False,
) -> _CandidateAnalysis:
    non_null = series.dropna()
    missing_ratio = 1 - (len(non_null) / max(len(series), 1))
    unique_count = int(non_null.nunique())
    blockers: list[str] = []
    reasons: list[str] = []
    score = 0.0

    if len(non_null) == 0:
        blockers.append("The column contains no observed target values.")
    elif unique_count < 2:
        blockers.append("The column has fewer than two distinct values.")
    if missing_ratio > 0.5:
        blockers.append("More than half of the target values are missing.")
    if _is_identifier(column, series):
        blockers.append("The column appears to be an identifier rather than an outcome.")

    normalized_name = _normalized(column)
    if explicit:
        score += 0.6
        reasons.append("The user explicitly selected this target.")
    if _objective_mentions_column(objective, column):
        score += 0.65
        reasons.append("The objective explicitly names this column.")
    if normalized_name in GENERIC_TARGET_NAMES:
        score += 0.45
        reasons.append("The column name is a common target label.")
    if normalized_name in SEMANTIC_TARGET_NAMES:
        score += 0.35
        reasons.append("The column name has outcome-oriented meaning.")
    if missing_ratio > 0:
        reasons.append(f"{missing_ratio:.1%} of target values are missing.")
    if blockers:
        score = min(score, 0.2)

    return _CandidateAnalysis(
        candidate=TargetCandidate(
            column=column,
            score=round(min(score, 1.0), 3),
            suitable=not blockers,
            reasons=reasons,
            blockers=blockers,
        ),
        missing_ratio=missing_ratio,
        unique_count=unique_count,
    )


def _target_candidates(df: pd.DataFrame, objective: str) -> list[_CandidateAnalysis]:
    analyzed = [_analyze_candidate(str(column), df[column], objective) for column in df.columns]
    relevant = [item for item in analyzed if item.candidate.score > 0 or item.candidate.blockers]
    return sorted(relevant, key=lambda item: (-item.candidate.score, item.candidate.column))


def _time_columns(df: pd.DataFrame) -> list[str]:
    candidates: list[str] = []
    for column in df.columns:
        name_tokens = set(_normalized(str(column)).split())
        if is_datetime64_any_dtype(df[column]) or name_tokens.intersection(TIME_NAME_PARTS):
            candidates.append(str(column))
    return candidates


def _evidence_hash(evidence: list[DecisionEvidence]) -> str:
    payload = [item.model_dump(mode="json") for item in evidence]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decision(
    *,
    task_type: TaskType,
    target_column: str | None,
    confidence: float,
    evidence: list[DecisionEvidence],
    candidates: list[_CandidateAnalysis],
    confidence_reasons: list[str],
    clarification_question: str | None = None,
    optional_suggestion: TaskSuggestion | None = None,
) -> TaskDecision:
    reasons = [item.message for item in evidence if item.effect in {"support", "block"}]
    return TaskDecision(
        task_type=task_type,
        target_column=target_column,
        confidence=round(max(0.0, min(confidence, 1.0)), 3),
        reasons=reasons,
        clarification_question=clarification_question,
        evidence=evidence,
        target_candidates=[item.candidate for item in candidates[:10]],
        confidence_reasons=confidence_reasons,
        requires_clarification=task_type == TaskType.NEEDS_CLARIFICATION,
        evidence_hash=_evidence_hash(evidence),
        optional_suggestion=optional_suggestion,
        suggestion_used=False,
    )


def _clarification(
    message: str,
    question: str,
    *,
    candidates: list[_CandidateAnalysis],
    optional_suggestion: TaskSuggestion | None,
    code: str = "clarification_required",
) -> TaskDecision:
    evidence = [DecisionEvidence(code=code, message=message, effect="block")]
    return _decision(
        task_type=TaskType.NEEDS_CLARIFICATION,
        target_column=None,
        confidence=0.98,
        evidence=evidence,
        candidates=candidates,
        confidence_reasons=["The deterministic evidence is insufficient for a safe decision."],
        clarification_question=question,
        optional_suggestion=optional_suggestion,
    )


def detect_task(
    df: pd.DataFrame,
    target_column: str | None = None,
    objective: str | None = None,
    optional_suggestion: TaskSuggestion | None = None,
) -> TaskDecision:
    """Return a deterministic task decision; optional suggestions are presentation-only."""

    objective_text = _normalized(objective or "")
    candidates = _target_candidates(df, objective_text)
    forecasting = any(word in objective_text for word in FORECAST_WORDS)

    selected: _CandidateAnalysis | None = None
    if target_column:
        if target_column not in df.columns:
            return _clarification(
                f"The requested target '{target_column}' is not present in the dataset.",
                "Which existing column should ZubePredict learn to predict?",
                candidates=candidates,
                optional_suggestion=optional_suggestion,
                code="target_missing",
            )
        selected = _analyze_candidate(
            target_column,
            df[target_column],
            objective_text,
            explicit=True,
        )
    elif forecasting or any(word in objective_text for word in SUPERVISED_WORDS):
        credible = [
            item for item in candidates if item.candidate.suitable and item.candidate.score >= 0.45
        ]
        if len(credible) > 1 and credible[0].candidate.score - credible[1].candidate.score < 0.25:
            names = ", ".join(item.candidate.column for item in credible[:5])
            return _clarification(
                f"Multiple credible target columns were found: {names}.",
                "Which one column should be the prediction target?",
                candidates=candidates,
                optional_suggestion=optional_suggestion,
                code="multiple_target_candidates",
            )
        if credible and selected is None:
            selected = credible[0]

    if forecasting:
        if selected is None:
            return _clarification(
                "The objective asks for forecasting but no credible target was identified.",
                "Which numeric column should be forecast?",
                candidates=candidates,
                optional_suggestion=optional_suggestion,
                code="forecast_target_missing",
            )
        if not selected.candidate.suitable:
            return _clarification(
                f"Forecast target '{selected.candidate.column}' is unsuitable.",
                "Choose a forecast target with observed numeric variation.",
                candidates=candidates,
                optional_suggestion=optional_suggestion,
                code="unsuitable_target",
            )
        time_columns = _time_columns(df)
        if not time_columns:
            return _clarification(
                "Forecasting was requested but no time-order column was identified.",
                "Which column contains the observation date or time?",
                candidates=candidates,
                optional_suggestion=optional_suggestion,
                code="time_column_missing",
            )
        evidence = [
            DecisionEvidence(
                code="forecast_objective",
                message="The stated objective explicitly requests forecasting over time.",
                effect="support",
            ),
            DecisionEvidence(
                code="forecast_time_column",
                message=f"Time-order evidence was found in: {', '.join(time_columns)}.",
                effect="support",
                value=time_columns[0],
            ),
            DecisionEvidence(
                code="selected_target",
                message=f"'{selected.candidate.column}' is the selected forecast target.",
                effect="support",
                value=selected.candidate.column,
            ),
        ]
        return _decision(
            task_type=TaskType.TIME_SERIES_FORECASTING,
            target_column=selected.candidate.column,
            confidence=0.9 if target_column else 0.84,
            evidence=evidence,
            candidates=candidates,
            confidence_reasons=[
                "Both an explicit forecasting intent and a time-order column are present.",
                "Confidence is higher when the target is explicitly confirmed.",
            ],
            optional_suggestion=optional_suggestion,
        )

    if selected is not None:
        candidate = selected.candidate
        if not candidate.suitable:
            return _clarification(
                f"Target '{candidate.column}' is unsuitable: {' '.join(candidate.blockers)}",
                "Choose a non-identifier target with enough observed variation.",
                candidates=[
                    selected,
                    *[item for item in candidates if item.candidate.column != candidate.column],
                ],
                optional_suggestion=optional_suggestion,
                code="unsuitable_target",
            )
        target = df[candidate.column].dropna()
        unique_count = int(target.nunique())
        if is_bool_dtype(target) or unique_count == 2:
            task_type = TaskType.BINARY_CLASSIFICATION
            signal = "The selected target contains exactly two distinct classes."
            code = "binary_target_cardinality"
        elif not is_numeric_dtype(target) or unique_count <= min(20, max(3, len(target) // 20)):
            task_type = TaskType.MULTICLASS_CLASSIFICATION
            signal = "The selected target contains a limited set of categorical outcomes."
            code = "categorical_target_cardinality"
        else:
            task_type = TaskType.REGRESSION
            signal = "The selected target is numeric with many distinct values."
            code = "continuous_numeric_target"
        evidence = [
            DecisionEvidence(
                code="selected_target",
                message=f"'{candidate.column}' is the selected target.",
                effect="support",
                value=candidate.column,
            ),
            DecisionEvidence(code=code, message=signal, effect="support", value=unique_count),
        ]
        if selected.missing_ratio > 0:
            evidence.append(
                DecisionEvidence(
                    code="target_missing_values",
                    message=f"The target is {selected.missing_ratio:.1%} missing.",
                    effect="concern",
                    value=round(selected.missing_ratio, 4),
                )
            )
        explicit = target_column is not None
        confidence = (0.93 if explicit else 0.83) - min(selected.missing_ratio * 0.2, 0.1)
        return _decision(
            task_type=task_type,
            target_column=candidate.column,
            confidence=confidence,
            evidence=evidence,
            candidates=[
                selected,
                *[item for item in candidates if item.candidate.column != candidate.column],
            ],
            confidence_reasons=[
                "The target's dtype and cardinality directly support this task family.",
                "The target was explicitly confirmed."
                if explicit
                else "The target was inferred from intent and semantic naming.",
            ],
            optional_suggestion=optional_suggestion,
        )

    if any(word in objective_text for word in ANOMALY_WORDS):
        evidence = [
            DecisionEvidence(
                code="anomaly_objective",
                message="The objective asks to find unusual records without a labelled outcome.",
                effect="support",
            )
        ]
        return _decision(
            task_type=TaskType.ANOMALY_DETECTION,
            target_column=None,
            confidence=0.86,
            evidence=evidence,
            candidates=candidates,
            confidence_reasons=["The anomaly intent is explicit and requires no target column."],
            optional_suggestion=optional_suggestion,
        )
    if any(word in objective_text for word in CLUSTER_WORDS):
        evidence = [
            DecisionEvidence(
                code="clustering_objective",
                message="The objective asks to group similar records without a labelled outcome.",
                effect="support",
            )
        ]
        return _decision(
            task_type=TaskType.CLUSTERING,
            target_column=None,
            confidence=0.86,
            evidence=evidence,
            candidates=candidates,
            confidence_reasons=["The grouping intent is explicit and requires no target column."],
            optional_suggestion=optional_suggestion,
        )

    return _clarification(
        "No confirmed target or clear clustering, anomaly, or forecasting intent was supplied.",
        "What should ZubePredict predict, or should it find clusters or unusual records?",
        candidates=candidates,
        optional_suggestion=optional_suggestion,
        code="objective_ambiguous",
    )

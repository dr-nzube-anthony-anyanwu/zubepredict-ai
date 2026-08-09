from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

from zubepredict_core.shared.schemas import DataQualityReport, QualityFinding

RiskKind = Literal["blocking", "warning"]

IDENTIFIER_TOKENS = {"id", "identifier", "uuid", "guid", "key"}
TIME_TOKENS = {"date", "time", "timestamp", "datetime", "month", "year", "week"}
POST_OUTCOME_TOKENS = {
    "after",
    "approved",
    "closed",
    "discharged",
    "final",
    "paid",
    "post",
    "result",
    "settled",
}
RISKY_OVERRIDE_CODES = {
    "suspected_identifier",
    "quasi_constant",
    "extreme_missingness",
    "high_cardinality",
    "near_perfect_target_proxy",
    "post_outcome_name_hint",
    "suspicious_date_feature",
}
NEAR_PERFECT_CORRELATION = 0.995


@dataclass(frozen=True)
class _FindingInput:
    code: str
    message: str
    columns: tuple[str, ...]
    metric: float | int | str | None
    suggested_action: str
    default_severity: RiskKind = "warning"
    risky_override: bool = False


def _tokens(column: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", column.lower()))


def _risk_id(code: str, columns: tuple[str, ...]) -> str:
    return f"{code}:{','.join(columns)}" if columns else code


def _looks_like_identifier(column: str, series: pd.Series, rows: int) -> bool:
    tokens = _tokens(column)
    non_null = series.dropna()
    unique_ratio = non_null.nunique() / max(len(non_null), 1)
    name_hint = bool(tokens.intersection(IDENTIFIER_TOKENS))
    generated_text_key = (
        not is_numeric_dtype(non_null) and len(non_null) >= 20 and unique_ratio > 0.98
    )
    return bool(name_hint or generated_text_key or (rows >= 20 and unique_ratio == 1 and name_hint))


def _looks_like_time(column: str, series: pd.Series) -> bool:
    if is_datetime64_any_dtype(series):
        return True
    if not _tokens(column).intersection(TIME_TOKENS):
        return False
    non_null = series.dropna()
    if non_null.empty:
        return False
    parsed = pd.to_datetime(non_null.astype(str), errors="coerce")
    return bool(parsed.notna().mean() >= 0.8 and parsed.nunique() > 1)


def _is_group_column(column: str, series: pd.Series, rows: int) -> bool:
    tokens = _tokens(column)
    if not tokens.intersection(IDENTIFIER_TOKENS):
        return False
    unique = series.nunique(dropna=True)
    return bool(rows >= 10 and 1 < unique < rows and unique / rows <= 0.5)


def _is_exact_target_copy(feature: pd.Series, target: pd.Series) -> bool:
    comparable = feature.notna() & target.notna()
    if comparable.sum() == 0:
        return False
    return bool(feature[comparable].astype(str).equals(target[comparable].astype(str)))


def _near_perfect_proxy(feature: pd.Series, target: pd.Series) -> float | None:
    comparable = feature.notna() & target.notna()
    if comparable.sum() < 10:
        return None
    left = feature[comparable]
    right = target[comparable]
    if is_numeric_dtype(left) and is_numeric_dtype(right):
        correlation = float(left.astype(float).corr(right.astype(float)))
        if np.isfinite(correlation) and NEAR_PERFECT_CORRELATION <= abs(correlation) <= 1:
            return round(abs(correlation), 6)
    feature_unique = int(left.nunique())
    target_unique = int(right.nunique())
    if 2 <= feature_unique <= 20 and 2 <= target_unique <= 20:
        frame = pd.DataFrame({"feature": left.astype(str), "target": right.astype(str)})
        forward = frame.groupby("feature")["target"].transform(
            lambda values: values.value_counts().index[0]
        )
        reverse = frame.groupby("target")["feature"].transform(
            lambda values: values.value_counts().index[0]
        )
        forward_accuracy = float((forward == frame["target"]).mean())
        reverse_accuracy = float((reverse == frame["feature"]).mean())
        proxy_score = min(forward_accuracy, reverse_accuracy)
        if proxy_score >= 0.98:
            return round(proxy_score, 6)
    return None


def _finding(
    item: _FindingInput,
    forced: set[str],
    acknowledged: set[str],
) -> QualityFinding:
    finding_id = _risk_id(item.code, item.columns)
    forced_risk = item.risky_override and bool(set(item.columns).intersection(forced))
    is_acknowledged = finding_id in acknowledged
    severity: RiskKind = item.default_severity
    message = item.message
    if forced_risk and not is_acknowledged:
        severity = "blocking"
        message += f" Forced inclusion requires acknowledgement '{finding_id}'."
    elif forced_risk and is_acknowledged:
        message += " The user explicitly acknowledged this risky inclusion."
    return QualityFinding(
        id=finding_id,
        code=item.code,
        severity=severity,
        message=message,
        columns=list(item.columns),
        metric=item.metric,
        suggested_action=item.suggested_action,
        requires_acknowledgement=forced_risk,
        acknowledged=forced_risk and is_acknowledged,
    )


def assess_data_quality(
    df: pd.DataFrame,
    *,
    target_column: str | None = None,
    forbidden_features: list[str] | None = None,
    forced_features: list[str] | None = None,
    acknowledged_risks: list[str] | None = None,
) -> DataQualityReport:
    """Build deterministic leakage and quality evidence without modifying data."""

    columns = [str(column) for column in df.columns]
    if len(set(columns)) != len(columns):
        raise ValueError("Dataset column names must be unique for quality assessment.")
    if target_column is not None and target_column not in df.columns:
        raise ValueError(f"Target '{target_column}' is not present in the dataset.")

    forbidden = set(forbidden_features or [])
    forced = set(forced_features or [])
    acknowledged = set(acknowledged_risks or [])
    unknown = sorted((forbidden | forced) - set(columns))
    if unknown:
        raise ValueError(f"Configured feature columns are missing: {', '.join(unknown)}.")
    if target_column and target_column in forced:
        raise ValueError("The target column can never be forced into model features.")

    inputs: list[_FindingInput] = []
    suggested_exclusions: set[str] = set(forbidden)
    group_columns: list[str] = []
    time_columns: list[str] = []
    rows = len(df)

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows:
        inputs.append(
            _FindingInput(
                "duplicate_rows",
                f"Found {duplicate_rows:,} exact duplicate rows.",
                (),
                duplicate_rows,
                "Deduplicate before validation so repeated records do not span folds.",
            )
        )

    target = df[target_column] if target_column else None
    if target is not None:
        target_missing_ratio = float(target.isna().mean()) if rows else 0.0
        if target_missing_ratio >= 0.5:
            inputs.append(
                _FindingInput(
                    "target_extreme_missingness",
                    f"Target '{target_column}' is {target_missing_ratio:.1%} missing.",
                    (target_column or "",),
                    round(target_missing_ratio, 6),
                    "Choose a better-observed target or repair target collection before training.",
                    "blocking",
                )
            )
    for column in columns:
        if column == target_column:
            continue
        series = df[column]
        non_null = series.dropna()
        unique = int(non_null.nunique())
        missing_ratio = float(series.isna().mean()) if rows else 0.0
        top_ratio = (
            float(non_null.value_counts(normalize=True).iloc[0]) if not non_null.empty else 1.0
        )

        if column in forbidden:
            inputs.append(
                _FindingInput(
                    "user_forbidden_feature",
                    f"'{column}' is explicitly forbidden by the user.",
                    (column,),
                    None,
                    "Exclude this feature from every training fold.",
                    "blocking" if column in forced else "warning",
                )
            )
            suggested_exclusions.add(column)
        if unique <= 1:
            inputs.append(
                _FindingInput(
                    "constant_feature",
                    f"'{column}' has fewer than two observed values.",
                    (column,),
                    unique,
                    "Exclude this feature because it contains no predictive variation.",
                    "blocking" if column in forced else "warning",
                )
            )
            suggested_exclusions.add(column)
            continue
        if top_ratio >= 0.98:
            inputs.append(
                _FindingInput(
                    "quasi_constant",
                    f"'{column}' has one value in {top_ratio:.1%} of observed rows.",
                    (column,),
                    round(top_ratio, 6),
                    "Exclude it unless its rare values are intentionally meaningful.",
                    risky_override=True,
                )
            )
            suggested_exclusions.add(column)
        if missing_ratio >= 0.8:
            inputs.append(
                _FindingInput(
                    "extreme_missingness",
                    f"'{column}' is {missing_ratio:.1%} missing.",
                    (column,),
                    round(missing_ratio, 6),
                    "Exclude it unless the missingness itself is understood and intended.",
                    risky_override=True,
                )
            )
            suggested_exclusions.add(column)
        if _looks_like_identifier(column, series, rows):
            inputs.append(
                _FindingInput(
                    "suspected_identifier",
                    f"'{column}' appears to identify records or entities.",
                    (column,),
                    round(unique / max(len(non_null), 1), 6),
                    "Exclude it from model features.",
                    risky_override=True,
                )
            )
            suggested_exclusions.add(column)
        if (
            not is_numeric_dtype(non_null)
            and unique >= 20
            and unique / max(len(non_null), 1) >= 0.5
        ):
            inputs.append(
                _FindingInput(
                    "high_cardinality",
                    f"'{column}' has {unique:,} distinct categorical values.",
                    (column,),
                    unique,
                    "Exclude it or use a leakage-safe encoding strategy.",
                    risky_override=True,
                )
            )
            suggested_exclusions.add(column)
        if _tokens(column).intersection(POST_OUTCOME_TOKENS):
            inputs.append(
                _FindingInput(
                    "post_outcome_name_hint",
                    f"'{column}' has a name associated with information known after an outcome.",
                    (column,),
                    None,
                    "Exclude it unless its availability at prediction time is confirmed.",
                    risky_override=True,
                )
            )
            suggested_exclusions.add(column)
        if _looks_like_time(column, series):
            time_columns.append(column)
            inputs.append(
                _FindingInput(
                    "suspicious_date_feature",
                    f"'{column}' contains ordered date/time values.",
                    (column,),
                    None,
                    "Use time-aware validation or exclude it from an ordinary random split.",
                    risky_override=True,
                )
            )
            suggested_exclusions.add(column)
        if _is_group_column(column, series, rows):
            group_columns.append(column)
            suggested_exclusions.add(column)
        if target is not None:
            if _is_exact_target_copy(series, target):
                inputs.append(
                    _FindingInput(
                        "exact_target_duplicate",
                        f"'{column}' exactly duplicates the target on observed rows.",
                        (column, target_column or ""),
                        None,
                        "Remove this direct leakage feature before training.",
                        "blocking",
                    )
                )
                suggested_exclusions.add(column)
            else:
                correlation = _near_perfect_proxy(series, target)
                if correlation is not None:
                    inputs.append(
                        _FindingInput(
                            "near_perfect_target_proxy",
                            f"'{column}' has near-perfect correlation with the target.",
                            (column,),
                            correlation,
                            "Exclude it unless its prediction-time availability is confirmed.",
                            risky_override=True,
                        )
                    )
                    suggested_exclusions.add(column)

    if group_columns:
        inputs.append(
            _FindingInput(
                "grouped_entities_detected",
                f"Repeated entity identifiers were found: {', '.join(group_columns)}.",
                tuple(group_columns),
                None,
                "Use group-aware validation so one entity cannot appear in train and validation.",
                "blocking",
            )
        )
    if time_columns:
        inputs.append(
            _FindingInput(
                "time_ordering_detected",
                f"Time ordering was found: {', '.join(time_columns)}.",
                tuple(time_columns),
                None,
                "Use chronological validation rather than an ordinary shuffled split.",
                "blocking",
            )
        )

    findings = [_finding(item, forced, acknowledged) for item in inputs]
    applicable_ids = {item.id for item in findings if item.requires_acknowledgement}
    unused_acknowledgements = sorted(acknowledged - applicable_ids)
    if unused_acknowledgements:
        raise ValueError(
            "Acknowledgements do not match a forced risky finding: "
            + ", ".join(unused_acknowledgements)
        )

    effective_exclusions = sorted(suggested_exclusions - forced)
    blocking = [item for item in findings if item.severity == "blocking"]
    warnings = [item for item in findings if item.severity == "warning"]
    canonical = json.dumps(
        {
            "target": target_column,
            "findings": [item.model_dump(mode="json") for item in findings],
            "exclusions": effective_exclusions,
            "forbidden": sorted(forbidden),
            "groups": group_columns,
            "times": time_columns,
            "acknowledged": sorted(acknowledged),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return DataQualityReport(
        rows=rows,
        columns=len(columns),
        target_column=target_column,
        findings=findings,
        blocking_errors=blocking,
        warnings=warnings,
        suggested_exclusions=effective_exclusions,
        forbidden_features=sorted(forbidden),
        group_columns=group_columns,
        time_columns=time_columns,
        acknowledged_risks=sorted(acknowledged),
        can_train=not blocking,
        evidence_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )

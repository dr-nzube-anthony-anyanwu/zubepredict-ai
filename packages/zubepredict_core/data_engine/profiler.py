from typing import Any

import pandas as pd

from zubepredict_core.data_engine.quality_guardian import assess_data_quality
from zubepredict_core.shared.schemas import ColumnProfile, DatasetProfile

TARGET_HINTS = {
    "target",
    "label",
    "outcome",
    "response",
    "class",
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
}


def _safe_sample(series: pd.Series, limit: int = 3) -> list[Any]:
    values = series.dropna().unique()[:limit].tolist()
    return [value.item() if hasattr(value, "item") else value for value in values]


def _looks_like_identifier(name: str, series: pd.Series, rows: int) -> bool:
    lowered = name.lower().strip()
    name_hint = lowered == "id" or lowered.endswith("_id") or lowered.startswith("id_")
    uniqueness_ratio = series.nunique(dropna=True) / max(rows, 1)
    return bool(name_hint or (uniqueness_ratio > 0.98 and series.dtype == "object"))


def profile_dataframe(df: pd.DataFrame) -> DatasetProfile:
    rows = len(df)
    profiles: list[ColumnProfile] = []
    possible_targets: list[str] = []
    warnings: list[str] = []

    for column in df.columns:
        series = df[column]
        missing_count = int(series.isna().sum())
        unique_count = int(series.nunique(dropna=True))
        lowered = str(column).lower().strip()
        is_identifier = _looks_like_identifier(str(column), series, rows)
        profiles.append(
            ColumnProfile(
                name=str(column),
                dtype=str(series.dtype),
                missing_count=missing_count,
                missing_percent=round((missing_count / max(rows, 1)) * 100, 2),
                unique_count=unique_count,
                sample_values=_safe_sample(series),
                suspected_identifier=is_identifier,
            )
        )
        if lowered in TARGET_HINTS or any(hint in lowered for hint in TARGET_HINTS):
            if not is_identifier:
                possible_targets.append(str(column))
        if missing_count / max(rows, 1) > 0.5:
            warnings.append(f"Column '{column}' is more than 50% missing.")
        if unique_count <= 1:
            warnings.append(f"Column '{column}' is constant and should normally be excluded.")

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows:
        warnings.append(f"Found {duplicate_rows:,} duplicate rows.")

    quality_report = assess_data_quality(df)
    return DatasetProfile(
        rows=rows,
        columns=len(df.columns),
        duplicate_rows=duplicate_rows,
        column_profiles=profiles,
        possible_targets=list(dict.fromkeys(possible_targets)),
        warnings=warnings,
        quality_report=quality_report,
    )

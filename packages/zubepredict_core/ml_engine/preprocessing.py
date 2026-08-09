from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


@dataclass(frozen=True)
class PreprocessingPlan:
    transformer: ColumnTransformer
    numeric_columns: list[str]
    categorical_columns: list[str]
    excluded_columns: list[str]


def build_preprocessor(
    features: pd.DataFrame,
    *,
    excluded_columns: list[str] | None = None,
    force_include: list[str] | None = None,
) -> PreprocessingPlan:
    forced = set(force_include or [])
    automatic = [
        str(column)
        for column in features.columns
        if str(column) not in forced
        and (
            features[column].nunique(dropna=True) <= 1
            or str(column).lower() == "id"
            or str(column).lower().endswith("_id")
        )
    ]
    excluded = list(dict.fromkeys([*automatic, *(excluded_columns or [])]))
    usable = features.drop(columns=excluded, errors="ignore")
    numeric = usable.select_dtypes(include="number").columns.astype(str).tolist()
    categorical = [str(column) for column in usable.columns if str(column) not in numeric]

    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", min_frequency=2)),
        ]
    )
    transformer = ColumnTransformer(
        [
            ("numeric", numeric_pipeline, numeric),
            ("categorical", categorical_pipeline, categorical),
        ],
        remainder="drop",
    )
    return PreprocessingPlan(transformer, numeric, categorical, excluded)

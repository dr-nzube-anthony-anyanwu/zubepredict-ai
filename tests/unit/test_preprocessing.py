import pandas as pd
from zubepredict_core.ml_engine.preprocessing import build_preprocessor


def test_identifier_is_excluded_from_preprocessing() -> None:
    features = pd.DataFrame(
        {
            "patient_id": ["p-1", "p-2", "p-3"],
            "age": [20, 30, 40],
        }
    )

    plan = build_preprocessor(features)

    assert "patient_id" in plan.excluded_columns
    assert "patient_id" not in plan.categorical_columns
    assert plan.numeric_columns == ["age"]


def test_explicitly_acknowledged_identifier_can_bypass_automatic_exclusion() -> None:
    features = pd.DataFrame(
        {
            "patient_id": [1, 2, 3],
            "age": [20, 30, 40],
        }
    )

    plan = build_preprocessor(features, force_include=["patient_id"])

    assert "patient_id" not in plan.excluded_columns
    assert plan.numeric_columns == ["patient_id", "age"]

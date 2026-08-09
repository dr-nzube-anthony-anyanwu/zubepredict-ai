import pandas as pd
from zubepredict_core.data_engine.task_detector import detect_task
from zubepredict_core.shared.schemas import TaskSuggestion, TaskType


def test_detects_binary_classification() -> None:
    df = pd.DataFrame({"age": [20, 30, 40, 50], "readmitted": ["no", "yes", "no", "yes"]})
    result = detect_task(df, target_column="readmitted")
    assert result.task_type == TaskType.BINARY_CLASSIFICATION


def test_detects_multiclass_classification() -> None:
    df = pd.DataFrame(
        {
            "age": list(range(60)),
            "risk_band": ["low", "medium", "high"] * 20,
        }
    )
    result = detect_task(df, target_column="risk_band")
    assert result.task_type == TaskType.MULTICLASS_CLASSIFICATION


def test_detects_regression() -> None:
    df = pd.DataFrame({"rooms": list(range(30)), "price": [value * 12.5 for value in range(30)]})
    result = detect_task(df, target_column="price")
    assert result.task_type == TaskType.REGRESSION


def test_requests_clarification_without_goal() -> None:
    df = pd.DataFrame({"age": [20, 30], "city": ["A", "B"]})
    result = detect_task(df)
    assert result.task_type == TaskType.NEEDS_CLARIFICATION
    assert result.clarification_question


def test_requests_clarification_for_ambiguous_objective() -> None:
    df = pd.DataFrame({"age": [20, 30], "city": ["A", "B"]})
    result = detect_task(df, objective="Analyze this dataset and find useful insights")
    assert result.task_type == TaskType.NEEDS_CLARIFICATION
    assert result.clarification_question


def test_detects_clustering_without_inventing_a_target() -> None:
    df = pd.DataFrame({"age": [20, 31, 46], "spend": [40, 90, 180]})
    result = detect_task(df, objective="Cluster similar customers into segments")

    assert result.task_type == TaskType.CLUSTERING
    assert result.target_column is None


def test_detects_anomaly_detection_without_inventing_a_target() -> None:
    df = pd.DataFrame({"amount": [10, 11, 900], "hour": [8, 9, 3]})
    result = detect_task(df, objective="Find unusual transactions and outliers")

    assert result.task_type == TaskType.ANOMALY_DETECTION
    assert result.target_column is None


def test_detects_forecasting_from_intent_target_and_time_evidence() -> None:
    df = pd.DataFrame(
        {
            "event_date": pd.date_range("2026-01-01", periods=30),
            "sales": list(range(30)),
        }
    )
    result = detect_task(df, objective="Forecast sales over time")

    assert result.task_type == TaskType.TIME_SERIES_FORECASTING
    assert result.target_column == "sales"
    assert {item.code for item in result.evidence} >= {
        "forecast_objective",
        "forecast_time_column",
    }


def test_clarifies_when_multiple_targets_are_equally_credible() -> None:
    df = pd.DataFrame(
        {
            "feature": range(30),
            "target": ["yes", "no"] * 15,
            "label": ["low", "medium", "high"] * 10,
        }
    )
    result = detect_task(df, objective="Predict target and label")

    assert result.task_type == TaskType.NEEDS_CLARIFICATION
    assert result.requires_clarification is True
    assert result.evidence[0].code == "multiple_target_candidates"


def test_semantic_target_is_inferred_with_a_reason_and_stable_hash() -> None:
    df = pd.DataFrame({"age": range(30), "churn": ["yes", "no"] * 15})
    first = detect_task(df, objective="Predict customer churn")
    second = detect_task(df, objective="Predict customer churn")

    assert first.task_type == TaskType.BINARY_CLASSIFICATION
    assert first.target_column == "churn"
    assert first.confidence_reasons
    assert len(first.evidence_hash) == 64
    assert first.evidence_hash == second.evidence_hash


def test_rejects_identifier_constant_and_majority_missing_targets() -> None:
    frames = (
        (pd.DataFrame({"customer_id": range(30), "x": range(30)}), "customer_id"),
        (pd.DataFrame({"constant": [1] * 30, "x": range(30)}), "constant"),
        (pd.DataFrame({"outcome": [None] * 20 + [0, 1] * 5}), "outcome"),
    )

    for frame, target in frames:
        result = detect_task(frame, target_column=target)
        assert result.task_type == TaskType.NEEDS_CLARIFICATION
        assert result.evidence[0].code == "unsuitable_target"


def test_optional_provider_suggestion_cannot_override_deterministic_evidence() -> None:
    df = pd.DataFrame({"age": range(30), "churn": ["yes", "no"] * 15})
    suggestion = TaskSuggestion(
        provider="hermes",
        task_type=TaskType.REGRESSION,
        target_column="age",
        rationale="A deliberately conflicting optional suggestion.",
    )
    result = detect_task(
        df,
        target_column="churn",
        objective="Predict churn",
        optional_suggestion=suggestion,
    )

    assert result.task_type == TaskType.BINARY_CLASSIFICATION
    assert result.optional_suggestion == suggestion
    assert result.suggestion_used is False

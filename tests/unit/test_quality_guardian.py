from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from zubepredict_core.data_engine.quality_guardian import assess_data_quality


def codes(report) -> set[str]:
    return {finding.code for finding in report.findings}


def test_detects_general_quality_risks_and_stable_evidence() -> None:
    rows = 100
    dataframe = pd.DataFrame(
        {
            "record_id": [f"r-{index}" for index in range(rows)],
            "constant": [1] * rows,
            "quasi": [0] * 98 + [1, 2],
            "mostly_missing": [None] * 80 + list(range(20)),
            "category": [f"category-{index}" for index in range(rows)],
            "value": list(range(rows)),
        }
    )
    dataframe = pd.concat([dataframe, dataframe.iloc[[0]]], ignore_index=True)

    first = assess_data_quality(dataframe)
    second = assess_data_quality(dataframe)

    assert {
        "duplicate_rows",
        "suspected_identifier",
        "constant_feature",
        "quasi_constant",
        "extreme_missingness",
        "high_cardinality",
    } <= codes(first)
    assert {"record_id", "constant", "quasi", "mostly_missing", "category"} <= set(
        first.suggested_exclusions
    )
    assert first.evidence_hash == second.evidence_hash


def test_exact_target_duplicate_is_a_hard_blocker() -> None:
    dataframe = pd.DataFrame({"age": range(30), "target": [0, 1] * 15, "target_copy": [0, 1] * 15})

    report = assess_data_quality(dataframe, target_column="target")

    assert report.can_train is False
    assert "exact_target_duplicate" in {finding.code for finding in report.blocking_errors}


def test_near_perfect_proxy_requires_exact_acknowledgement_when_forced() -> None:
    target = np.arange(100, dtype=float)
    dataframe = pd.DataFrame(
        {
            "feature": np.sin(target),
            "target": target,
            "proxy": (target * 3.0) + np.where(target % 2 == 0, 0.01, -0.01),
        }
    )
    default = assess_data_quality(dataframe, target_column="target")
    unacknowledged = assess_data_quality(
        dataframe,
        target_column="target",
        forced_features=["proxy"],
    )
    acknowledged = assess_data_quality(
        dataframe,
        target_column="target",
        forced_features=["proxy"],
        acknowledged_risks=["near_perfect_target_proxy:proxy"],
    )

    assert "proxy" in default.suggested_exclusions
    assert unacknowledged.can_train is False
    risk = next(item for item in acknowledged.findings if item.code == "near_perfect_target_proxy")
    assert acknowledged.can_train is True
    assert risk.acknowledged is True
    assert "proxy" not in acknowledged.suggested_exclusions


def test_detects_near_bijective_categorical_proxy() -> None:
    target = (["yes"] * 50) + (["no"] * 50)
    proxy = (["approved"] * 49) + ["denied"] + (["denied"] * 50)
    dataframe = pd.DataFrame({"feature": range(100), "target": target, "decision": proxy})

    report = assess_data_quality(dataframe, target_column="target")

    assert "near_perfect_target_proxy" in codes(report)
    assert "decision" in report.suggested_exclusions


def test_detects_post_outcome_names_and_user_forbidden_features() -> None:
    dataframe = pd.DataFrame(
        {
            "age": range(30),
            "final_result": ["pass", "fail"] * 15,
            "target": ["yes", "no"] * 15,
        }
    )

    report = assess_data_quality(
        dataframe,
        target_column="target",
        forbidden_features=["age"],
    )

    assert {"post_outcome_name_hint", "user_forbidden_feature"} <= codes(report)
    assert {"final_result", "age"} <= set(report.suggested_exclusions)


def test_grouped_entities_and_time_ordering_block_random_validation() -> None:
    dataframe = pd.DataFrame(
        {
            "patient_id": [f"p-{index // 3}" for index in range(30)],
            "visit_date": pd.date_range("2026-01-01", periods=30),
            "value": range(30),
            "target": [0, 1] * 15,
        }
    )

    report = assess_data_quality(dataframe, target_column="target")

    assert report.group_columns == ["patient_id"]
    assert report.time_columns == ["visit_date"]
    assert {"grouped_entities_detected", "time_ordering_detected"} <= {
        finding.code for finding in report.blocking_errors
    }


def test_target_extreme_missingness_blocks_training() -> None:
    dataframe = pd.DataFrame({"feature": range(20), "target": [None] * 12 + [0, 1] * 4})

    report = assess_data_quality(dataframe, target_column="target")

    assert "target_extreme_missingness" in {item.code for item in report.blocking_errors}


def test_rejects_unused_or_mismatched_acknowledgement() -> None:
    dataframe = pd.DataFrame({"feature": range(30), "target": [0, 1] * 15})

    with pytest.raises(ValueError, match="do not match"):
        assess_data_quality(
            dataframe,
            target_column="target",
            acknowledged_risks=["suspected_identifier:feature"],
        )

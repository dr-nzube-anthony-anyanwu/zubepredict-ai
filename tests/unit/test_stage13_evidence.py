from __future__ import annotations

from uuid import UUID

from zubepredict_core.evidence import (
    build_evidence_envelope,
    deterministic_evidence_summary,
    grounded_or_fallback_narrative,
    verify_evidence_envelope,
)


def _evidence():
    return build_evidence_envelope(
        experiment_id=UUID("33333333-3333-4333-8333-333333333333"),
        dataset_fingerprint="b" * 64,
        constitution_version=2,
        result_summary={
            "task_type": "binary_classification",
            "validation_strategy": "stratified_cross_validation",
            "primary_metric": "pr_auc",
            "winner": "logistic_regression",
            "leaderboard": [
                {"model_name": "logistic_regression", "pr_auc": 0.81},
            ],
        },
        warnings=[],
    )


def test_evidence_envelope_is_hash_addressed_and_frozen() -> None:
    evidence = _evidence()

    assert len(evidence.evidence_hash) == 64
    assert verify_evidence_envelope(evidence)
    assert evidence.model_leaderboard[0]["pr_auc"] == 0.81


def test_ungrounded_numbers_or_models_fall_back_to_verified_summary() -> None:
    evidence = _evidence()
    fallback = deterministic_evidence_summary(evidence)

    assert (
        grounded_or_fallback_narrative(evidence, "Random forest scored 99.9 percent.") == fallback
    )
    assert (
        grounded_or_fallback_narrative(evidence, "logistic_regression recorded pr_auc 0.81.")
        == "logistic_regression recorded pr_auc 0.81."
    )

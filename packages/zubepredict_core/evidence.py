from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceEnvelope(BaseModel):
    """Immutable, hash-addressed evidence supplied to language layers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_version: str = "2.0"
    experiment_id: UUID
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    constitution_version: int = Field(ge=1)
    task_type: str
    target: str | None = None
    exclusions: list[str] = Field(default_factory=list, max_length=100)
    validation_strategy: str
    primary_metric: str
    secondary_metrics: dict[str, Any] = Field(default_factory=dict)
    model_leaderboard: list[dict[str, Any]] = Field(max_length=20)
    winner: str | None = None
    calibration_error_analysis: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    intended_use_warning: str
    reproducibility: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_evidence_envelope(
    *,
    experiment_id: UUID,
    dataset_fingerprint: str,
    constitution_version: int,
    result_summary: dict[str, Any],
    warnings: list[Any],
    constitution: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> EvidenceEnvelope:
    leaderboard = result_summary.get("leaderboard")
    bounded_leaderboard = leaderboard[:20] if isinstance(leaderboard, list) else []
    task = result_summary.get("task")
    task_payload = task if isinstance(task, dict) else {}
    limitations = [
        "Metrics describe the recorded validation procedure, not future performance.",
        "Prediction does not establish causation.",
    ]
    raw_limitations = result_summary.get("limitations")
    if isinstance(raw_limitations, list):
        limitations.extend(str(item)[:500] for item in raw_limitations[:28])
    constitution_payload = constitution if isinstance(constitution, dict) else {}
    winner_name = result_summary.get("winner")
    winner_row = next(
        (
            item
            for item in bounded_leaderboard
            if isinstance(item, dict) and item.get("model_name") == winner_name
        ),
        {},
    )
    raw_metrics = winner_row.get("metrics") if isinstance(winner_row, dict) else {}
    metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
    primary_metric = str(result_summary.get("primary_metric") or "")
    secondary_metrics = {key: value for key, value in metrics.items() if key != primary_metric}
    analysis = {
        key: result_summary[key]
        for key in ("calibration", "threshold_analysis", "error_analysis_summary")
        if result_summary.get(key) is not None
    }
    reproducibility = {
        "random_seed": result_summary.get("random_seed"),
        "software_versions": result_summary.get("software_versions", {}),
        "winner_hyperparameters": winner_row.get("hyperparameters", {})
        if isinstance(winner_row, dict)
        else {},
        "validation_strategy": str(result_summary.get("validation_strategy") or ""),
    }
    generated = generated_at or datetime.now(UTC)
    generated_value = generated.astimezone(UTC).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "evidence_version": "2.0",
        "experiment_id": str(experiment_id),
        "dataset_fingerprint": dataset_fingerprint,
        "constitution_version": constitution_version,
        "task_type": str(task_payload.get("task_type") or result_summary.get("task_type") or ""),
        "target": task_payload.get("target_column") or result_summary.get("target"),
        "exclusions": [
            str(item)[:255] for item in constitution_payload.get("exclusions", [])[:100]
        ],
        "validation_strategy": str(result_summary.get("validation_strategy") or ""),
        "primary_metric": primary_metric,
        "secondary_metrics": secondary_metrics,
        "model_leaderboard": bounded_leaderboard,
        "winner": winner_name,
        "calibration_error_analysis": analysis,
        "warnings": [str(item)[:500] for item in warnings[:50]],
        "limitations": limitations[:30],
        "intended_use_warning": str(
            constitution_payload.get("intended_use_warning")
            or "Decision support and research use only unless independently validated."
        )[:1000],
        "reproducibility": reproducibility,
        "generated_at": generated_value,
    }
    payload["evidence_hash"] = _canonical_hash(payload)
    return EvidenceEnvelope.model_validate(payload)


def verify_evidence_envelope(evidence: EvidenceEnvelope) -> bool:
    payload = evidence.model_dump(mode="json", exclude={"evidence_hash"})
    expected = _canonical_hash(payload)
    return hmac.compare_digest(expected, evidence.evidence_hash)


def deterministic_evidence_summary(evidence: EvidenceEnvelope) -> str:
    if evidence.winner and evidence.primary_metric:
        return (
            f"The recorded winner is {evidence.winner} using "
            f"{evidence.primary_metric} under "
            f"{evidence.validation_strategy or 'the recorded validation'}; "
            f"see evidence {evidence.evidence_hash}."
        )
    return f"Verified evidence is available as {evidence.evidence_hash}; no winner is recorded."


def grounded_or_fallback_narrative(evidence: EvidenceEnvelope, narrative: str) -> str:
    """Reject model names or numbers not grounded in the immutable evidence."""

    canonical = json.dumps(evidence.model_dump(mode="json"), sort_keys=True).lower()
    candidate = narrative.strip()
    if not candidate:
        return deterministic_evidence_summary(evidence)

    evidence_models = {
        str(item.get("model_name", "")).strip().lower()
        for item in evidence.model_leaderboard
        if isinstance(item, dict) and item.get("model_name")
    }
    if evidence.winner:
        evidence_models.add(evidence.winner.lower())
    model_mentions = set(
        re.findall(r"\b[a-z][a-z0-9_.-]*(?:\s+[a-z0-9_.-]+){0,3}\b", candidate.lower())
    )
    suspicious_models = {
        phrase
        for phrase in model_mentions
        if any(token in phrase for token in ("forest", "boost", "regression", "svm", "catboost"))
        and not any(model in phrase or phrase in model for model in evidence_models)
    }
    if suspicious_models:
        return deterministic_evidence_summary(evidence)

    for number in re.findall(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?%?", candidate):
        normalized = number.rstrip("%").lstrip("-")
        if normalized and normalized not in canonical:
            return deterministic_evidence_summary(evidence)
    return candidate

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from zubepredict_core.decisions import overrides
from zubepredict_core.decisions.overrides import DecisionOverrideError, TaskOverrideService
from zubepredict_core.repositories.models import AuditLogRecord, DatasetRecord, ExperimentRecord
from zubepredict_core.shared.config import Settings
from zubepredict_core.shared.schemas import TaskType


class Experiments:
    def __init__(self, experiment: ExperimentRecord | None) -> None:
        self.experiment = experiment

    def get(self, _experiment_id):
        return self.experiment

    def update_decision(self, _experiment_id, **values):
        assert self.experiment is not None
        self.experiment = self.experiment.model_copy(
            update={
                "detected_task": values["detected_task"],
                "target_column": values["target_column"],
                "task_confidence": values["task_confidence"],
                "decision_evidence": values["decision_evidence"],
                "decision_source": values["decision_source"],
                "decision_version": values["expected_version"] + 1,
                "task_override_confirmed_at": values["override_confirmed_at"],
            }
        )
        return self.experiment


class Audits:
    def __init__(self, owner_id) -> None:
        self.owner_id = owner_id
        self.events: list[AuditLogRecord] = []

    def record(self, **values):
        event = AuditLogRecord(
            id=len(self.events) + 1,
            owner_id=self.owner_id,
            created_at=datetime.now(UTC),
            **values,
        )
        self.events.append(event)
        return event

    def list_for_resource(self, **_values):
        return self.events


def make_service(monkeypatch):
    owner_id = uuid4()
    project_id = uuid4()
    dataset_id = uuid4()
    experiment = ExperimentRecord(
        id=uuid4(),
        owner_id=owner_id,
        project_id=project_id,
        dataset_id=dataset_id,
        detected_task=TaskType.REGRESSION.value,
        target_column="price",
        task_confidence=0.88,
    )
    dataset = DatasetRecord(
        id=dataset_id,
        owner_id=owner_id,
        project_id=project_id,
        original_filename="data.csv",
        storage_path=f"{owner_id}/data.csv",
        sha256="a" * 64,
        size_bytes=100,
        profile={"schema_columns": ["price", "churn", "age"]},
    )
    experiments = Experiments(experiment)
    audits = Audits(owner_id)
    repositories = SimpleNamespace(
        experiments=experiments,
        datasets=SimpleNamespace(get=lambda _dataset_id: dataset),
        audit_logs=audits,
    )
    monkeypatch.setattr(overrides, "create_service_repositories", lambda *_args: repositories)
    service = TaskOverrideService(
        Settings(_env_file=None),
        SimpleNamespace(user_id=owner_id),
        repositories,
    )
    return service, experiment, experiments, audits


def test_override_requires_explicit_confirmation(monkeypatch) -> None:
    service, experiment, _experiments, audits = make_service(monkeypatch)

    with pytest.raises(DecisionOverrideError, match="explicitly confirm"):
        service.confirm_override(
            experiment.id,
            task_type=TaskType.BINARY_CLASSIFICATION,
            target_column="churn",
            rationale="The user confirmed churn is the labelled outcome.",
            confirmed_by_user=False,
        )
    assert audits.events == []


def test_override_validates_target_against_dataset_schema(monkeypatch) -> None:
    service, experiment, _experiments, _audits = make_service(monkeypatch)

    with pytest.raises(DecisionOverrideError, match="validated dataset schema"):
        service.confirm_override(
            experiment.id,
            task_type=TaskType.BINARY_CLASSIFICATION,
            target_column="missing_column",
            rationale="The user selected a target that does not exist.",
            confirmed_by_user=True,
        )


def test_unsupervised_override_rejects_a_target(monkeypatch) -> None:
    service, experiment, _experiments, _audits = make_service(monkeypatch)

    with pytest.raises(DecisionOverrideError, match="do not use a target"):
        service.confirm_override(
            experiment.id,
            task_type=TaskType.CLUSTERING,
            target_column="price",
            rationale="The user wants unsupervised customer grouping.",
            confirmed_by_user=True,
        )


def test_confirmed_override_is_versioned_and_audited(monkeypatch) -> None:
    service, experiment, experiments, audits = make_service(monkeypatch)

    updated = service.confirm_override(
        experiment.id,
        task_type=TaskType.BINARY_CLASSIFICATION,
        target_column="churn",
        rationale="The user confirmed churn is the labelled outcome.",
        confirmed_by_user=True,
    )

    assert updated.detected_task == TaskType.BINARY_CLASSIFICATION.value
    assert updated.target_column == "churn"
    assert updated.decision_source == "user_override"
    assert updated.decision_version == 2
    assert updated.task_override_confirmed_at is not None
    assert len(updated.decision_evidence["evidence_hash"]) == 64
    assert [event.action for event in audits.events] == [
        "experiment.task_override_requested",
        "experiment.task_override_applied",
    ]
    assert service.history(experiment.id) == audits.events
    assert experiments.experiment == updated


def test_cross_user_or_missing_experiment_cannot_be_overridden(monkeypatch) -> None:
    service, experiment, _experiments, _audits = make_service(monkeypatch)
    service._repositories.experiments.experiment = None

    with pytest.raises(DecisionOverrideError, match="not found or is not owned"):
        service.confirm_override(
            experiment.id,
            task_type=TaskType.BINARY_CLASSIFICATION,
            target_column="churn",
            rationale="A different user must not change this experiment.",
            confirmed_by_user=True,
        )

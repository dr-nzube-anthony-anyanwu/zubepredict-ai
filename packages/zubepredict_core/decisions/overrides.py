from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from zubepredict_core.repositories.models import AuditLogRecord, ExperimentRecord
from zubepredict_core.repositories.supabase import (
    AuthenticatedSupabaseSession,
    SupabaseRepositorySet,
    create_service_repositories,
)
from zubepredict_core.shared.config import Settings
from zubepredict_core.shared.schemas import TaskType

SUPERVISED_TASKS = {
    TaskType.BINARY_CLASSIFICATION,
    TaskType.MULTICLASS_CLASSIFICATION,
    TaskType.REGRESSION,
    TaskType.TIME_SERIES_FORECASTING,
}
UNSUPERVISED_TASKS = {TaskType.CLUSTERING, TaskType.ANOMALY_DETECTION}


class DecisionOverrideError(ValueError):
    """Raised when a requested task override is unsafe or incomplete."""


class TaskOverrideService:
    def __init__(
        self,
        settings: Settings,
        session: AuthenticatedSupabaseSession,
        repositories: SupabaseRepositorySet,
    ) -> None:
        self._settings = settings
        self._session = session
        self._repositories = repositories

    def confirm_override(
        self,
        experiment_id: UUID,
        *,
        task_type: TaskType,
        target_column: str | None,
        rationale: str,
        confirmed_by_user: bool,
    ) -> ExperimentRecord:
        if not confirmed_by_user:
            raise DecisionOverrideError("The user must explicitly confirm a task override.")
        cleaned_rationale = rationale.strip()
        if len(cleaned_rationale) < 10 or len(cleaned_rationale) > 1000:
            raise DecisionOverrideError("Override rationale must contain 10 to 1000 characters.")
        if task_type == TaskType.NEEDS_CLARIFICATION:
            raise DecisionOverrideError("Clarification is a state, not a task override.")

        experiment = self._repositories.experiments.get(experiment_id)
        if experiment is None:
            raise DecisionOverrideError(
                "The experiment was not found or is not owned by this user."
            )
        dataset = self._repositories.datasets.get(experiment.dataset_id)
        if dataset is None:
            raise DecisionOverrideError("The experiment's owned dataset was not found.")
        schema_columns = self._schema_columns(dataset.profile)

        cleaned_target = target_column.strip() if target_column else None
        if task_type in SUPERVISED_TASKS:
            if not cleaned_target:
                raise DecisionOverrideError("This task override requires a target column.")
            if cleaned_target not in schema_columns:
                raise DecisionOverrideError(
                    f"Target '{cleaned_target}' is not present in the validated dataset schema."
                )
        elif task_type in UNSUPERVISED_TASKS and cleaned_target is not None:
            raise DecisionOverrideError("Clustering and anomaly detection do not use a target.")

        if (
            experiment.detected_task == task_type.value
            and experiment.target_column == cleaned_target
        ):
            raise DecisionOverrideError("The requested override does not change the decision.")

        confirmed_at = datetime.now(UTC)
        evidence = {
            "source": "user_override",
            "confirmed": True,
            "rationale": cleaned_rationale,
            "previous": {
                "task_type": experiment.detected_task,
                "target_column": experiment.target_column,
                "decision_version": experiment.decision_version,
            },
            "override": {
                "task_type": task_type.value,
                "target_column": cleaned_target,
            },
        }
        canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        evidence["evidence_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        trusted = create_service_repositories(self._settings, self._session.user_id)
        audit_metadata = {
            "previous_task": experiment.detected_task,
            "previous_target": experiment.target_column,
            "override_task": task_type.value,
            "override_target": cleaned_target,
            "rationale": cleaned_rationale,
            "expected_version": experiment.decision_version,
            "evidence_hash": evidence["evidence_hash"],
        }
        trusted.audit_logs.record(
            action="experiment.task_override_requested",
            resource_type="experiment",
            resource_id=experiment.id,
            metadata=audit_metadata,
        )
        updated = trusted.experiments.update_decision(
            experiment.id,
            expected_version=experiment.decision_version,
            detected_task=task_type.value,
            target_column=cleaned_target,
            task_confidence=1.0,
            decision_evidence=evidence,
            decision_source="user_override",
            override_confirmed_at=confirmed_at,
        )
        trusted.audit_logs.record(
            action="experiment.task_override_applied",
            resource_type="experiment",
            resource_id=experiment.id,
            metadata={**audit_metadata, "decision_version": updated.decision_version},
        )
        return updated

    def history(self, experiment_id: UUID) -> list[AuditLogRecord]:
        if self._repositories.experiments.get(experiment_id) is None:
            raise DecisionOverrideError(
                "The experiment was not found or is not owned by this user."
            )
        return self._repositories.audit_logs.list_for_resource(
            resource_type="experiment", resource_id=experiment_id
        )

    @staticmethod
    def _schema_columns(profile: dict | None) -> list[str]:
        if not profile:
            raise DecisionOverrideError(
                "The dataset has no validated schema; finalize it before overriding the task."
            )
        columns = profile.get("schema_columns")
        if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns):
            raise DecisionOverrideError(
                "The dataset has no validated schema; finalize it before overriding the task."
            )
        return columns

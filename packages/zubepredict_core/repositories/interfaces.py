from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from zubepredict_core.repositories.models import (
    AuditLogRecord,
    DatasetRecord,
    ExperimentRecord,
    ModelRunRecord,
    ProjectRecord,
    ReportRecord,
)


class ProjectRepository(Protocol):
    def create(
        self, *, name: str, description: str | None = None, source_channel: str = "api"
    ) -> ProjectRecord: ...

    def get(self, project_id: UUID) -> ProjectRecord | None: ...

    def list(self) -> list[ProjectRecord]: ...

    def delete(self, project_id: UUID) -> None: ...


class DatasetRepository(Protocol):
    def register(
        self,
        *,
        project_id: UUID,
        original_filename: str,
        storage_path: str,
        sha256: str,
        size_bytes: int,
        row_count: int | None = None,
        column_count: int | None = None,
        profile: dict[str, Any] | None = None,
        media_type: str = "application/octet-stream",
        file_format: str = "csv",
        retention_status: str = "active",
        retention_expires_at: datetime | None = None,
        source_channel: str = "api",
    ) -> DatasetRecord: ...

    def get(self, dataset_id: UUID) -> DatasetRecord | None: ...

    def get_by_storage_path(self, storage_path: str) -> DatasetRecord | None: ...

    def get_by_fingerprint(self, project_id: UUID, sha256: str) -> DatasetRecord | None: ...

    def list_for_project(self, project_id: UUID) -> list[DatasetRecord]: ...

    def delete(self, dataset_id: UUID) -> None: ...

    def set_retention_status(self, dataset_id: UUID, status: str) -> DatasetRecord: ...


class ExperimentRepository(Protocol):
    def create(
        self,
        *,
        project_id: UUID,
        dataset_id: UUID,
        objective: str | None = None,
        target_column: str | None = None,
        configuration: dict[str, Any] | None = None,
        source_channel: str = "api",
    ) -> ExperimentRecord: ...

    def get(self, experiment_id: UUID) -> ExperimentRecord | None: ...

    def list_for_project(self, project_id: UUID) -> list[ExperimentRecord]: ...


class ExperimentWriterRepository(ExperimentRepository, Protocol):
    def update_decision(
        self,
        experiment_id: UUID,
        *,
        expected_version: int,
        detected_task: str,
        target_column: str | None,
        task_confidence: float,
        decision_evidence: dict[str, Any],
        decision_source: str,
        override_confirmed_at: datetime | None = None,
    ) -> ExperimentRecord: ...


class ModelRunRepository(Protocol):
    def get(self, run_id: UUID) -> ModelRunRecord | None: ...

    def list_for_experiment(self, experiment_id: UUID) -> list[ModelRunRecord]: ...


class ModelRunWriterRepository(ModelRunRepository, Protocol):
    def record(
        self,
        *,
        experiment_id: UUID,
        model_name: str,
        hyperparameters: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        fold_scores: list[Any] | None = None,
        fit_seconds: float | None = None,
        predict_seconds: float | None = None,
        status: str = "pending",
        error_message: str | None = None,
        artifact_path: str | None = None,
    ) -> ModelRunRecord: ...


class ReportRepository(Protocol):
    def get(self, report_id: UUID) -> ReportRecord | None: ...

    def list_for_experiment(self, experiment_id: UUID) -> list[ReportRecord]: ...


class ReportWriterRepository(ReportRepository, Protocol):
    def create(
        self,
        *,
        experiment_id: UUID,
        report_type: str,
        storage_path: str,
        report_version: int = 1,
        filename: str | None = None,
        content_type: str | None = None,
        size_bytes: int | None = None,
        sha256: str | None = None,
        evidence_hash: str | None = None,
        integrity_metadata: dict[str, Any] | None = None,
    ) -> ReportRecord: ...


class AuditRepository(Protocol):
    def list_for_resource(
        self, *, resource_type: str, resource_id: UUID
    ) -> list[AuditLogRecord]: ...


class AuditWriterRepository(AuditRepository, Protocol):
    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLogRecord: ...

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RepositoryRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    owner_id: UUID
    created_at: datetime | None = None


class ProjectRecord(RepositoryRecord):
    name: str
    description: str | None = None
    source_channel: str = "api"
    updated_at: datetime | None = None


class DatasetRecord(RepositoryRecord):
    project_id: UUID
    original_filename: str
    storage_path: str
    sha256: str
    size_bytes: int
    row_count: int | None = None
    column_count: int | None = None
    profile: dict[str, Any] | None = None
    media_type: str = "application/octet-stream"
    file_format: str = "csv"
    source_channel: str = "api"
    retention_status: str = "active"
    retention_expires_at: datetime | None = None
    validated_at: datetime | None = None
    updated_at: datetime | None = None


class ExperimentRecord(RepositoryRecord):
    project_id: UUID
    dataset_id: UUID
    objective: str | None = None
    target_column: str | None = None
    detected_task: str | None = None
    task_confidence: float | None = None
    primary_metric: str | None = None
    winner_model: str | None = None
    status: str = "draft"
    progress: int = 0
    warnings: list[Any] = Field(default_factory=list)
    error_message: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    decision_evidence: dict[str, Any] = Field(default_factory=dict)
    decision_source: str = "deterministic"
    decision_version: int = 1
    decision_updated_at: datetime | None = None
    task_override_confirmed_at: datetime | None = None
    job_id: UUID | None = None
    idempotency_key: str | None = None
    queued_at: datetime | None = None
    heartbeat_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    attempt_count: int = 0
    state_version: int = 1
    result_summary: dict[str, Any] = Field(default_factory=dict)
    source_channel: str = "api"


class ModelRunRecord(RepositoryRecord):
    experiment_id: UUID
    job_id: UUID | None = None
    model_name: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    fold_scores: list[Any] = Field(default_factory=list)
    fit_seconds: float | None = None
    predict_seconds: float | None = None
    status: str = "pending"
    error_message: str | None = None
    artifact_path: str | None = None


class ReportRecord(RepositoryRecord):
    experiment_id: UUID
    report_type: str
    storage_path: str
    report_version: int = 1
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    evidence_hash: str | None = None
    integrity_metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    owner_id: UUID
    action: str
    resource_type: str
    resource_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from supabase import Client, create_client
from supabase.client import ClientOptions

from zubepredict_core.repositories.models import (
    AuditLogRecord,
    DatasetRecord,
    ExperimentRecord,
    ModelRunRecord,
    ProjectRecord,
    ReportRecord,
)
from zubepredict_core.shared.config import Settings

RecordT = TypeVar("RecordT", bound=BaseModel)


class SupabaseConfigurationError(RuntimeError):
    """Raised when an optional Supabase repository is used without configuration."""


class SupabaseRepositoryError(RuntimeError):
    """Raised when the Data API rejects a repository operation."""


@dataclass(frozen=True)
class AuthenticatedSupabaseSession:
    client: Client
    user_id: UUID


class _OwnedSupabaseRepository(Generic[RecordT]):
    table_name: str
    record_type: type[RecordT]

    def __init__(self, session: AuthenticatedSupabaseSession) -> None:
        self._client = session.client
        self._owner_id = session.user_id

    def _execute(self, query: Any, action: str) -> Any:
        try:
            return query.execute()
        except Exception as exc:
            raise SupabaseRepositoryError(
                f"Supabase could not {action} {self.table_name}."
            ) from exc

    def _record(self, data: dict[str, Any]) -> RecordT:
        return self.record_type.model_validate(data)

    def _get(self, record_id: UUID) -> RecordT | None:
        query = (
            self._client.table(self.table_name)
            .select("*")
            .eq("id", str(record_id))
            .eq("owner_id", str(self._owner_id))
            .limit(1)
        )
        response = self._execute(query, "read")
        data = response.data or []
        return self._record(data[0]) if data else None

    def _list(self, **filters: UUID) -> list[RecordT]:
        query = self._client.table(self.table_name).select("*").eq("owner_id", str(self._owner_id))
        for column, value in filters.items():
            query = query.eq(column, str(value))
        response = self._execute(query.order("created_at", desc=True), "list")
        return [self._record(item) for item in (response.data or [])]

    def _insert(self, payload: dict[str, Any]) -> RecordT:
        owned_payload = {**payload, "owner_id": str(self._owner_id)}
        response = self._execute(
            self._client.table(self.table_name).insert(owned_payload), "create"
        )
        data = response.data or []
        if not data:
            raise SupabaseRepositoryError(
                f"Supabase created no visible {self.table_name} record. Check RLS policies."
            )
        return self._record(data[0])

    def _delete(self, record_id: UUID) -> None:
        query = (
            self._client.table(self.table_name)
            .delete()
            .eq("id", str(record_id))
            .eq("owner_id", str(self._owner_id))
        )
        self._execute(query, "delete")

    def _update(self, record_id: UUID, payload: dict[str, Any]) -> RecordT:
        query = (
            self._client.table(self.table_name)
            .update(payload)
            .eq("id", str(record_id))
            .eq("owner_id", str(self._owner_id))
        )
        response = self._execute(query, "update")
        data = response.data or []
        if not data:
            raise SupabaseRepositoryError(f"Supabase updated no owned {self.table_name} record.")
        return self._record(data[0])


class SupabaseProjectRepository(_OwnedSupabaseRepository[ProjectRecord]):
    table_name = "projects"
    record_type = ProjectRecord

    def create(self, *, name: str, description: str | None = None) -> ProjectRecord:
        return self._insert({"name": name, "description": description})

    def get(self, project_id: UUID) -> ProjectRecord | None:
        return self._get(project_id)

    def list(self) -> list[ProjectRecord]:
        return self._list()

    def delete(self, project_id: UUID) -> None:
        self._delete(project_id)


class SupabaseDatasetRepository(_OwnedSupabaseRepository[DatasetRecord]):
    table_name = "datasets"
    record_type = DatasetRecord

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
    ) -> DatasetRecord:
        return self._insert(
            {
                "project_id": str(project_id),
                "original_filename": original_filename,
                "storage_path": storage_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "row_count": row_count,
                "column_count": column_count,
                "profile": profile,
                "media_type": media_type,
                "file_format": file_format,
                "retention_status": retention_status,
                "retention_expires_at": retention_expires_at.isoformat()
                if retention_expires_at
                else None,
                "validated_at": datetime.now(UTC).isoformat(),
            }
        )

    def get(self, dataset_id: UUID) -> DatasetRecord | None:
        return self._get(dataset_id)

    def get_by_storage_path(self, storage_path: str) -> DatasetRecord | None:
        query = (
            self._client.table(self.table_name)
            .select("*")
            .eq("storage_path", storage_path)
            .eq("owner_id", str(self._owner_id))
            .limit(1)
        )
        response = self._execute(query, "read")
        data = response.data or []
        return self._record(data[0]) if data else None

    def list_for_project(self, project_id: UUID) -> list[DatasetRecord]:
        return self._list(project_id=project_id)

    def delete(self, dataset_id: UUID) -> None:
        self._delete(dataset_id)

    def set_retention_status(self, dataset_id: UUID, status: str) -> DatasetRecord:
        return self._update(
            dataset_id,
            {"retention_status": status, "updated_at": datetime.now(UTC).isoformat()},
        )


class SupabaseExperimentRepository(_OwnedSupabaseRepository[ExperimentRecord]):
    table_name = "experiments"
    record_type = ExperimentRecord

    def create(
        self,
        *,
        project_id: UUID,
        dataset_id: UUID,
        objective: str | None = None,
        target_column: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> ExperimentRecord:
        return self._insert(
            {
                "project_id": str(project_id),
                "dataset_id": str(dataset_id),
                "objective": objective,
                "target_column": target_column,
                "configuration": configuration or {},
            }
        )

    def create_job(
        self,
        *,
        project_id: UUID,
        dataset_id: UUID,
        job_id: UUID,
        idempotency_key: str,
        objective: str | None = None,
        target_column: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> ExperimentRecord:
        now = datetime.now(UTC).isoformat()
        return self._insert(
            {
                "project_id": str(project_id),
                "dataset_id": str(dataset_id),
                "job_id": str(job_id),
                "idempotency_key": idempotency_key,
                "objective": objective,
                "target_column": target_column,
                "configuration": configuration or {},
                "status": "queued",
                "progress": 0,
                "queued_at": now,
                "heartbeat_at": now,
            }
        )

    def get_by_idempotency_key(self, key: str) -> ExperimentRecord | None:
        query = (
            self._client.table(self.table_name)
            .select("*")
            .eq("owner_id", str(self._owner_id))
            .eq("idempotency_key", key)
            .limit(1)
        )
        response = self._execute(query, "read idempotent")
        data = response.data or []
        return self._record(data[0]) if data else None

    def claim_job(self, experiment_id: UUID, job_id: UUID) -> ExperimentRecord | None:
        now = datetime.now(UTC).isoformat()
        current = self.get(experiment_id)
        if current is None:
            return None
        query = (
            self._client.table(self.table_name)
            .update(
                {
                    "status": "profiling",
                    "progress": 5,
                    "heartbeat_at": now,
                    "started_at": now,
                    "attempt_count": current.attempt_count + 1,
                    "state_version": current.state_version + 1,
                }
            )
            .eq("id", str(experiment_id))
            .eq("owner_id", str(self._owner_id))
            .eq("job_id", str(job_id))
            .eq("status", "queued")
        )
        response = self._execute(query, "claim")
        data = response.data or []
        return self._record(data[0]) if data else None

    def resume_job(
        self,
        experiment_id: UUID,
        job_id: UUID,
        *,
        resume_payload: dict[str, Any],
        configuration: dict[str, Any],
    ) -> ExperimentRecord:
        """Atomically requeue the same interrupted job and LangGraph thread."""

        current = self.get(experiment_id)
        if current is None or current.job_id != job_id:
            raise SupabaseRepositoryError("The experiment job was not found.")
        if current.status != "needs_clarification":
            raise SupabaseRepositoryError(
                "Only an experiment waiting for clarification can be resumed."
            )
        now = datetime.now(UTC).isoformat()
        query = (
            self._client.table(self.table_name)
            .update(
                {
                    "status": "queued",
                    "configuration": configuration,
                    "result_summary": {"workflow_resume_payload": resume_payload},
                    "error_message": None,
                    "queued_at": now,
                    "heartbeat_at": now,
                    "state_version": current.state_version + 1,
                }
            )
            .eq("id", str(experiment_id))
            .eq("owner_id", str(self._owner_id))
            .eq("job_id", str(job_id))
            .eq("status", "needs_clarification")
            .eq("state_version", current.state_version)
        )
        response = self._execute(query, "resume")
        data = response.data or []
        if not data:
            raise SupabaseRepositoryError(
                "The clarification was already handled or changed concurrently."
            )
        return self._record(data[0])

    def update_job(
        self,
        experiment_id: UUID,
        job_id: UUID,
        *,
        status: str,
        progress: int,
        **fields: Any,
    ) -> ExperimentRecord:
        current = self.get(experiment_id)
        if current is None:
            raise SupabaseRepositoryError("The experiment job was not found.")
        payload = {
            "status": status,
            "progress": progress,
            "heartbeat_at": datetime.now(UTC).isoformat(),
            "state_version": current.state_version + 1,
            **fields,
        }
        query = (
            self._client.table(self.table_name)
            .update(payload)
            .eq("id", str(experiment_id))
            .eq("owner_id", str(self._owner_id))
            .eq("job_id", str(job_id))
            .eq("state_version", current.state_version)
        )
        response = self._execute(query, "update job")
        data = response.data or []
        if not data:
            raise SupabaseRepositoryError("Supabase updated no matching experiment job.")
        return self._record(data[0])

    def request_cancel(self, experiment_id: UUID) -> ExperimentRecord:
        experiment = self.get(experiment_id)
        if experiment is None:
            raise SupabaseRepositoryError("The experiment was not found or is not owned.")
        if experiment.status in {"completed", "failed", "cancelled"}:
            return experiment
        now = datetime.now(UTC).isoformat()
        payload: dict[str, Any] = {"cancel_requested_at": now, "heartbeat_at": now}
        if experiment.status in {"queued", "needs_clarification"}:
            payload.update(status="cancelled", completed_at=now)
        return self._update(experiment_id, payload)

    def list_stale(self, stale_after_seconds: int) -> list[ExperimentRecord]:
        cutoff = (datetime.now(UTC) - timedelta(seconds=stale_after_seconds)).isoformat()
        query = (
            self._client.table(self.table_name)
            .select("*")
            .in_("status", ["profiling", "training", "evaluating", "reporting"])
            .lt("heartbeat_at", cutoff)
        )
        response = self._execute(query, "list stale")
        return [self._record(item) for item in (response.data or [])]

    def recover_stale_job(self, stale: ExperimentRecord) -> bool:
        if stale.job_id is None:
            return False
        query = (
            self._client.table(self.table_name)
            .update(
                {
                    "status": "queued",
                    "heartbeat_at": datetime.now(UTC).isoformat(),
                    "state_version": stale.state_version + 1,
                    "error_message": "Recovered after a stale worker heartbeat.",
                }
            )
            .eq("id", str(stale.id))
            .eq("owner_id", str(self._owner_id))
            .eq("job_id", str(stale.job_id))
            .eq("status", stale.status)
            .eq("state_version", stale.state_version)
        )
        response = self._execute(query, "recover stale")
        return bool(response.data)

    def get(self, experiment_id: UUID) -> ExperimentRecord | None:
        return self._get(experiment_id)

    def list_for_project(self, project_id: UUID) -> list[ExperimentRecord]:
        return self._list(project_id=project_id)

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
    ) -> ExperimentRecord:
        now = datetime.now(UTC).isoformat()
        payload = {
            "detected_task": detected_task,
            "target_column": target_column,
            "task_confidence": task_confidence,
            "decision_evidence": decision_evidence,
            "decision_source": decision_source,
            "decision_version": expected_version + 1,
            "decision_updated_at": now,
            "task_override_confirmed_at": override_confirmed_at.isoformat()
            if override_confirmed_at
            else None,
        }
        query = (
            self._client.table(self.table_name)
            .update(payload)
            .eq("id", str(experiment_id))
            .eq("owner_id", str(self._owner_id))
            .eq("decision_version", expected_version)
        )
        response = self._execute(query, "update decision for")
        data = response.data or []
        if not data:
            raise SupabaseRepositoryError(
                "The experiment decision changed concurrently or is not owned by this user."
            )
        return self._record(data[0])


class SupabaseModelRunRepository(_OwnedSupabaseRepository[ModelRunRecord]):
    table_name = "model_runs"
    record_type = ModelRunRecord

    def record(
        self,
        *,
        experiment_id: UUID,
        job_id: UUID | None = None,
        model_name: str,
        hyperparameters: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        fold_scores: list[Any] | None = None,
        fit_seconds: float | None = None,
        predict_seconds: float | None = None,
        status: str = "pending",
        error_message: str | None = None,
        artifact_path: str | None = None,
    ) -> ModelRunRecord:
        return self._insert(
            {
                "experiment_id": str(experiment_id),
                "job_id": str(job_id) if job_id else None,
                "model_name": model_name,
                "hyperparameters": hyperparameters or {},
                "metrics": metrics or {},
                "fold_scores": fold_scores or [],
                "fit_seconds": fit_seconds,
                "predict_seconds": predict_seconds,
                "status": status,
                "error_message": error_message,
                "artifact_path": artifact_path,
            }
        )

    def delete_for_job(self, experiment_id: UUID, job_id: UUID) -> None:
        query = (
            self._client.table(self.table_name)
            .delete()
            .eq("owner_id", str(self._owner_id))
            .eq("experiment_id", str(experiment_id))
            .eq("job_id", str(job_id))
        )
        self._execute(query, "delete prior job runs from")

    def get(self, run_id: UUID) -> ModelRunRecord | None:
        return self._get(run_id)

    def list_for_experiment(self, experiment_id: UUID) -> list[ModelRunRecord]:
        return self._list(experiment_id=experiment_id)


class SupabaseReportRepository(_OwnedSupabaseRepository[ReportRecord]):
    table_name = "reports"
    record_type = ReportRecord

    def create(
        self,
        *,
        experiment_id: UUID,
        report_type: str,
        storage_path: str,
    ) -> ReportRecord:
        return self._insert(
            {
                "experiment_id": str(experiment_id),
                "report_type": report_type,
                "storage_path": storage_path,
            }
        )

    def get(self, report_id: UUID) -> ReportRecord | None:
        return self._get(report_id)

    def list_for_experiment(self, experiment_id: UUID) -> list[ReportRecord]:
        return self._list(experiment_id=experiment_id)


class SupabaseAuditRepository(_OwnedSupabaseRepository[AuditLogRecord]):
    table_name = "audit_logs"
    record_type = AuditLogRecord

    def list_for_resource(self, *, resource_type: str, resource_id: UUID) -> list[AuditLogRecord]:
        query = (
            self._client.table(self.table_name)
            .select("*")
            .eq("owner_id", str(self._owner_id))
            .eq("resource_type", resource_type)
            .eq("resource_id", str(resource_id))
            .order("created_at")
        )
        response = self._execute(query, "list")
        return [self._record(item) for item in (response.data or [])]

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLogRecord:
        return self._insert(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "metadata": metadata or {},
            }
        )


@dataclass(frozen=True)
class SupabaseRepositorySet:
    projects: SupabaseProjectRepository
    datasets: SupabaseDatasetRepository
    experiments: SupabaseExperimentRepository
    model_runs: SupabaseModelRunRepository
    reports: SupabaseReportRepository
    audit_logs: SupabaseAuditRepository

    @classmethod
    def from_session(cls, session: AuthenticatedSupabaseSession) -> SupabaseRepositorySet:
        return cls(
            projects=SupabaseProjectRepository(session),
            datasets=SupabaseDatasetRepository(session),
            experiments=SupabaseExperimentRepository(session),
            model_runs=SupabaseModelRunRepository(session),
            reports=SupabaseReportRepository(session),
            audit_logs=SupabaseAuditRepository(session),
        )


def _client_options(access_token: str | None = None) -> ClientOptions:
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    return ClientOptions(
        headers=headers,
        auto_refresh_token=False,
        persist_session=False,
    )


def create_authenticated_repositories(
    settings: Settings, access_token: str
) -> SupabaseRepositorySet:
    return SupabaseRepositorySet.from_session(create_authenticated_session(settings, access_token))


def create_authenticated_session(
    settings: Settings, access_token: str
) -> AuthenticatedSupabaseSession:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise SupabaseConfigurationError(
            "SUPABASE_URL and SUPABASE_ANON_KEY are required for authenticated repositories."
        )
    if not access_token.strip():
        raise SupabaseConfigurationError("A user access token is required.")

    client = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=_client_options(access_token),
    )
    try:
        response = client.auth.get_user(access_token)
        if response is None or response.user is None:
            raise ValueError("Supabase returned no authenticated user.")
        user_id = UUID(str(response.user.id))
    except Exception as exc:
        raise SupabaseRepositoryError("Supabase could not validate the user access token.") from exc

    return AuthenticatedSupabaseSession(client=client, user_id=user_id)


def create_service_repositories(settings: Settings, owner_id: UUID) -> SupabaseRepositorySet:
    """Create server-only repositories. The service-role client bypasses RLS."""

    return SupabaseRepositorySet.from_session(create_service_session(settings, owner_id))


def create_service_session(settings: Settings, owner_id: UUID) -> AuthenticatedSupabaseSession:
    """Create a server-only session. Its client bypasses RLS."""

    service_key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not service_key:
        raise SupabaseConfigurationError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required on the trusted server."
        )
    client = create_client(
        settings.supabase_url,
        service_key,
        options=_client_options(),
    )
    return AuthenticatedSupabaseSession(client=client, user_id=owner_id)

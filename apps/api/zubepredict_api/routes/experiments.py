from __future__ import annotations

import hashlib
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from zubepredict_core.repositories.models import ExperimentRecord
from zubepredict_core.repositories.supabase import (
    AuthenticatedSupabaseSession,
    SupabaseConfigurationError,
    SupabaseRepositoryError,
    SupabaseRepositorySet,
    create_authenticated_session,
    create_service_repositories,
)
from zubepredict_core.shared.config import get_settings
from zubepredict_core.shared.schemas import TaskType

from apps.worker.tasks import run_experiment

router = APIRouter(prefix="/experiments", tags=["experiments"])
bearer = HTTPBearer(auto_error=False)


class ExperimentJobRequest(BaseModel):
    project_id: UUID
    dataset_id: UUID
    objective: str | None = Field(default=None, max_length=2000)
    target_column: str | None = Field(default=None, max_length=255)
    configuration: dict[str, Any] = Field(default_factory=dict)


class ExperimentJobResponse(BaseModel):
    id: UUID
    job_id: UUID
    project_id: UUID
    dataset_id: UUID
    status: str
    progress: int
    attempt_count: int
    cancel_requested: bool
    error_message: str | None
    result_summary: dict[str, Any]
    reused: bool = False


class ExperimentResumeRequest(BaseModel):
    configuration: dict[str, Any] = Field(default_factory=dict)
    task_type: TaskType | None = None
    target_column: str | None = Field(default=None, max_length=255)
    confirmed_by_user: bool = False


def _session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedSupabaseSession:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A bearer access token is required.")
    try:
        return create_authenticated_session(get_settings(), credentials.credentials)
    except SupabaseConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The access token is invalid.") from exc


def _response(experiment: ExperimentRecord, *, reused: bool = False) -> ExperimentJobResponse:
    if experiment.job_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This experiment is not an asynchronous job.")
    return ExperimentJobResponse(
        id=experiment.id,
        job_id=experiment.job_id,
        project_id=experiment.project_id,
        dataset_id=experiment.dataset_id,
        status=experiment.status,
        progress=experiment.progress,
        attempt_count=experiment.attempt_count,
        cancel_requested=experiment.cancel_requested_at is not None,
        error_message=experiment.error_message,
        result_summary=experiment.result_summary,
        reused=reused,
    )


@router.post("/jobs", response_model=ExperimentJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    request: ExperimentJobRequest,
    response: Response,
    session: Annotated[AuthenticatedSupabaseSession, Depends(_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> ExperimentJobResponse:
    owned = SupabaseRepositorySet.from_session(session)
    project = owned.projects.get(request.project_id)
    dataset = owned.datasets.get(request.dataset_id)
    if project is None or dataset is None or dataset.project_id != project.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The project/dataset pair was not found or is not owned by this user.",
        )
    if dataset.retention_status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "The dataset is not active.")

    key_hash = hashlib.sha256(f"{session.user_id}:{idempotency_key}".encode()).hexdigest()
    trusted = create_service_repositories(get_settings(), session.user_id)
    existing = trusted.experiments.get_by_idempotency_key(key_hash)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _response(existing, reused=True)

    job_id = uuid4()
    try:
        experiment = trusted.experiments.create_job(
            project_id=request.project_id,
            dataset_id=request.dataset_id,
            job_id=job_id,
            idempotency_key=key_hash,
            objective=request.objective,
            target_column=request.target_column,
            configuration=request.configuration,
        )
    except SupabaseRepositoryError:
        concurrent = trusted.experiments.get_by_idempotency_key(key_hash)
        if concurrent is None:
            raise
        response.status_code = status.HTTP_200_OK
        return _response(concurrent, reused=True)

    try:
        run_experiment.send(str(experiment.id), str(session.user_id), str(job_id))
    except Exception as exc:
        trusted.experiments.update_job(
            experiment.id,
            job_id,
            status="failed",
            progress=0,
            error_message="The job could not be queued. It is safe to retry with a new key.",
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The job queue is unavailable."
        ) from exc
    return _response(experiment)


@router.get("/{experiment_id}", response_model=ExperimentJobResponse)
def get_job(
    experiment_id: UUID,
    session: Annotated[AuthenticatedSupabaseSession, Depends(_session)],
) -> ExperimentJobResponse:
    experiment = SupabaseRepositorySet.from_session(session).experiments.get(experiment_id)
    if experiment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The experiment was not found.")
    return _response(experiment)


@router.post(
    "/{experiment_id}/resume",
    response_model=ExperimentJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_job(
    experiment_id: UUID,
    request: ExperimentResumeRequest,
    session: Annotated[AuthenticatedSupabaseSession, Depends(_session)],
) -> ExperimentJobResponse:
    owned_repositories = SupabaseRepositorySet.from_session(session)
    owned = owned_repositories.experiments.get(experiment_id)
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The experiment was not found.")
    if owned.job_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This experiment has no resumable job.")
    if request.task_type == TaskType.NEEDS_CLARIFICATION:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Clarification is a workflow state, not a task type.",
        )
    if (request.task_type is not None or request.target_column is not None) and not (
        request.confirmed_by_user
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A task decision must be explicitly confirmed by the user.",
        )
    if request.target_column is not None and request.task_type is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A target clarification must include its confirmed task type.",
        )
    supervised_tasks = {
        TaskType.BINARY_CLASSIFICATION,
        TaskType.MULTICLASS_CLASSIFICATION,
        TaskType.REGRESSION,
        TaskType.TIME_SERIES_FORECASTING,
    }
    if request.task_type in supervised_tasks:
        dataset = owned_repositories.datasets.get(owned.dataset_id)
        schema_columns = (dataset.profile or {}).get("schema_columns") if dataset else None
        if not request.target_column or not isinstance(schema_columns, list) or (
            request.target_column not in schema_columns
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "The confirmed supervised task requires a target in the validated schema.",
            )
    if request.task_type in {TaskType.CLUSTERING, TaskType.ANOMALY_DETECTION} and (
        request.target_column is not None
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Clustering and anomaly detection do not use a target column.",
        )
    resume_payload: dict[str, Any] = {"configuration": request.configuration}
    if request.task_type is not None or request.target_column is not None:
        resume_payload.update(
            task_type=request.task_type.value if request.task_type else None,
            target_column=request.target_column,
            confirmed_by_user=request.confirmed_by_user,
        )
    trusted = create_service_repositories(get_settings(), session.user_id)
    try:
        resumed = trusted.experiments.resume_job(
            experiment_id,
            owned.job_id,
            resume_payload=resume_payload,
            configuration={**owned.configuration, **request.configuration},
        )
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    try:
        run_experiment.send(str(experiment_id), str(session.user_id), str(owned.job_id))
    except Exception as exc:
        trusted.experiments.update_job(
            experiment_id,
            owned.job_id,
            status="needs_clarification",
            progress=owned.progress,
            error_message="The resume request could not be queued; it is safe to retry.",
            result_summary=owned.result_summary,
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The job queue is unavailable."
        ) from exc
    return _response(resumed)


@router.post("/{experiment_id}/cancel", response_model=ExperimentJobResponse)
def cancel_job(
    experiment_id: UUID,
    session: Annotated[AuthenticatedSupabaseSession, Depends(_session)],
) -> ExperimentJobResponse:
    if SupabaseRepositorySet.from_session(session).experiments.get(experiment_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The experiment was not found.")
    try:
        experiment = create_service_repositories(
            get_settings(), session.user_id
        ).experiments.request_cancel(experiment_id)
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _response(experiment)

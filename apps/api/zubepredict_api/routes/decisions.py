from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from zubepredict_core.decisions import DecisionOverrideError, TaskOverrideService
from zubepredict_core.repositories.supabase import (
    SupabaseConfigurationError,
    SupabaseRepositoryError,
    SupabaseRepositorySet,
    create_authenticated_session,
)
from zubepredict_core.shared.config import get_settings
from zubepredict_core.shared.schemas import TaskType

router = APIRouter(prefix="/decisions/experiments", tags=["decisions"])
bearer = HTTPBearer(auto_error=False)


class TaskOverrideRequest(BaseModel):
    task_type: TaskType
    target_column: str | None = Field(default=None, max_length=255)
    rationale: str = Field(min_length=10, max_length=1000)
    confirmed_by_user: bool


class TaskOverrideResponse(BaseModel):
    experiment_id: UUID
    task_type: str
    target_column: str | None
    confidence: float
    decision_source: str
    decision_version: int


class AuditEventResponse(BaseModel):
    id: int
    action: str
    resource_type: str
    resource_id: UUID | None
    metadata: dict[str, Any]


def _service(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> TaskOverrideService:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A bearer access token is required.")
    settings = get_settings()
    try:
        session = create_authenticated_session(settings, credentials.credentials)
    except SupabaseConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The access token is invalid.") from exc
    return TaskOverrideService(settings, session, SupabaseRepositorySet.from_session(session))


@router.post("/{experiment_id}/override", response_model=TaskOverrideResponse)
def confirm_override(
    experiment_id: UUID,
    request: TaskOverrideRequest,
    service: Annotated[TaskOverrideService, Depends(_service)],
) -> TaskOverrideResponse:
    try:
        experiment = service.confirm_override(
            experiment_id,
            task_type=request.task_type,
            target_column=request.target_column,
            rationale=request.rationale,
            confirmed_by_user=request.confirmed_by_user,
        )
    except DecisionOverrideError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return TaskOverrideResponse(
        experiment_id=experiment.id,
        task_type=experiment.detected_task or "",
        target_column=experiment.target_column,
        confidence=experiment.task_confidence or 0,
        decision_source=experiment.decision_source,
        decision_version=experiment.decision_version,
    )


@router.get("/{experiment_id}/history", response_model=list[AuditEventResponse])
def override_history(
    experiment_id: UUID,
    service: Annotated[TaskOverrideService, Depends(_service)],
) -> list[AuditEventResponse]:
    try:
        events = service.history(experiment_id)
    except DecisionOverrideError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return [AuditEventResponse.model_validate(event, from_attributes=True) for event in events]

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from zubepredict_api.security.quotas import enforce_user_rate
from zubepredict_core.datasets import DatasetFileError, DatasetLifecycleError
from zubepredict_core.datasets.lifecycle import DatasetLifecycleService
from zubepredict_core.repositories.supabase import (
    SupabaseConfigurationError,
    SupabaseRepositoryError,
)
from zubepredict_core.shared.config import get_settings

router = APIRouter(prefix="/datasets", tags=["datasets"])
bearer = HTTPBearer(auto_error=False)


class PrepareUploadRequest(BaseModel):
    project_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=150)
    privacy_attested: bool = False


class UploadIntentResponse(BaseModel):
    project_id: UUID
    storage_path: str
    original_filename: str
    media_type: str
    file_format: str
    signed_upload_url: str
    upload_token: str
    expires_in_seconds: int


class FinalizeUploadRequest(BaseModel):
    project_id: UUID
    storage_path: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=150)
    privacy_attested: bool = False


class DatasetPreviewResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    rows_truncated: bool
    columns_truncated: bool


class FinalizedDatasetResponse(BaseModel):
    dataset_id: UUID
    project_id: UUID
    original_filename: str
    storage_path: str
    sha256: str
    size_bytes: int
    row_count: int
    column_count: int
    media_type: str
    file_format: str
    retention_status: str
    preview: DatasetPreviewResponse


def _service(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> DatasetLifecycleService:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A bearer access token is required.")
    try:
        service = DatasetLifecycleService.from_access_token(
            get_settings(), credentials.credentials
        )
        enforce_user_rate(service.owner_id)
        return service
    except SupabaseConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The access token is invalid.") from exc


@router.post("/upload-intents", response_model=UploadIntentResponse, status_code=201)
def prepare_upload(
    request: PrepareUploadRequest,
    service: Annotated[DatasetLifecycleService, Depends(_service)],
) -> UploadIntentResponse:
    try:
        intent = service.prepare_upload(
            project_id=request.project_id,
            filename=request.filename,
            content_type=request.content_type,
            privacy_attested=request.privacy_attested,
        )
        return UploadIntentResponse.model_validate(intent, from_attributes=True)
    except DatasetFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except DatasetLifecycleError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/finalize", response_model=FinalizedDatasetResponse)
def finalize_upload(
    request: FinalizeUploadRequest,
    service: Annotated[DatasetLifecycleService, Depends(_service)],
) -> FinalizedDatasetResponse:
    try:
        finalized = service.finalize_upload(
            project_id=request.project_id,
            storage_path=request.storage_path,
            filename=request.filename,
            content_type=request.content_type,
            privacy_attested=request.privacy_attested,
        )
    except DatasetFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except DatasetLifecycleError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    dataset = finalized.dataset
    return FinalizedDatasetResponse(
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        original_filename=dataset.original_filename,
        storage_path=dataset.storage_path,
        sha256=dataset.sha256,
        size_bytes=dataset.size_bytes,
        row_count=finalized.inspection.row_count,
        column_count=finalized.inspection.column_count,
        media_type=dataset.media_type,
        file_format=dataset.file_format,
        retention_status=dataset.retention_status,
        preview=DatasetPreviewResponse.model_validate(
            finalized.inspection.preview, from_attributes=True
        ),
    )


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: UUID,
    service: Annotated[DatasetLifecycleService, Depends(_service)],
) -> Response:
    try:
        service.delete_dataset(dataset_id)
    except DatasetLifecycleError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Protocol, cast
from uuid import UUID, uuid4

import httpx

from zubepredict_core.datasets.files import (
    DatasetFileError,
    DatasetInspection,
    StreamedFile,
    UploadMetadata,
    inspect_dataset,
    stream_to_file,
    validate_file_signature,
    validate_upload_metadata,
)
from zubepredict_core.repositories.models import DatasetRecord
from zubepredict_core.repositories.supabase import (
    AuthenticatedSupabaseSession,
    SupabaseRepositorySet,
    create_authenticated_session,
    create_service_repositories,
    create_service_session,
)
from zubepredict_core.shared.config import Settings


class DatasetLifecycleError(RuntimeError):
    """Raised when a secure dataset lifecycle operation cannot complete."""


@dataclass(frozen=True)
class UploadIntent:
    project_id: UUID
    storage_path: str
    original_filename: str
    media_type: str
    file_format: str
    signed_upload_url: str
    upload_token: str
    expires_in_seconds: int = 7200


@dataclass(frozen=True)
class FinalizedDataset:
    dataset: DatasetRecord
    inspection: DatasetInspection


@dataclass(frozen=True)
class IngestedDataset:
    dataset: DatasetRecord
    inspection: DatasetInspection | None
    duplicate: bool


class DatasetObjectStorage(Protocol):
    def create_upload_url(self, path: str) -> tuple[str, str]: ...

    def download_to(self, path: str, destination: BinaryIO, max_bytes: int) -> StreamedFile: ...

    def delete(self, path: str) -> None: ...

    def upload(self, path: str, content: bytes, content_type: str) -> None: ...


class SupabaseDatasetObjectStorage:
    def __init__(
        self,
        session: AuthenticatedSupabaseSession,
        bucket: str,
        *,
        timeout_seconds: float = 60,
    ) -> None:
        self._bucket = session.client.storage.from_(bucket)
        self._timeout_seconds = timeout_seconds

    def create_upload_url(self, path: str) -> tuple[str, str]:
        response = self._bucket.create_signed_upload_url(path)
        signed_url = response.get("signed_url") or response.get("signedUrl")
        token = response.get("token")
        if not signed_url or not token:
            raise DatasetLifecycleError("Supabase returned an incomplete signed upload URL.")
        return str(signed_url), str(token)

    def _download_chunks(self, signed_url: str, max_bytes: int) -> Iterable[bytes]:
        with httpx.stream("GET", signed_url, timeout=self._timeout_seconds) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise DatasetFileError(f"File exceeds the {max_bytes} byte upload limit.")
            yield from response.iter_bytes(chunk_size=64 * 1024)

    def download_to(self, path: str, destination: BinaryIO, max_bytes: int) -> StreamedFile:
        response = self._bucket.create_signed_url(path, 60)
        signed_url = response.get("signedURL") or response.get("signedUrl")
        if not signed_url:
            raise DatasetLifecycleError("Supabase returned no signed download URL.")
        return stream_to_file(
            self._download_chunks(str(signed_url), max_bytes), destination, max_bytes
        )

    def delete(self, path: str) -> None:
        self._bucket.remove([path])

    def upload(self, path: str, content: bytes, content_type: str) -> None:
        self._bucket.upload(
            path,
            content,
            {"content-type": content_type, "upsert": "false"},
        )


class DatasetLifecycleService:
    def __init__(
        self,
        settings: Settings,
        session: AuthenticatedSupabaseSession,
        repositories: SupabaseRepositorySet,
        storage: DatasetObjectStorage,
    ) -> None:
        self._settings = settings
        self._session = session
        self._repositories = repositories
        self._storage = storage

    @classmethod
    def from_access_token(cls, settings: Settings, access_token: str) -> DatasetLifecycleService:
        session = create_authenticated_session(settings, access_token)
        repositories = SupabaseRepositorySet.from_session(session)
        storage = SupabaseDatasetObjectStorage(session, settings.supabase_datasets_bucket)
        return cls(settings, session, repositories, storage)

    @classmethod
    def from_service_principal(cls, settings: Settings, owner_id: UUID) -> DatasetLifecycleService:
        session = create_service_session(settings, owner_id)
        repositories = SupabaseRepositorySet.from_session(session)
        storage = SupabaseDatasetObjectStorage(session, settings.supabase_datasets_bucket)
        return cls(settings, session, repositories, storage)

    def ingest_chunks(
        self,
        *,
        project_id: UUID,
        filename: str,
        content_type: str,
        chunks: Iterable[bytes],
        source_channel: str = "api",
    ) -> IngestedDataset:
        project = self._repositories.projects.get(project_id)
        if project is None:
            raise DatasetLifecycleError("The project was not found or is not owned by this user.")
        metadata = validate_upload_metadata(filename, content_type)
        temporary_path: Path | None = None
        storage_path: str | None = None
        uploaded = False
        try:
            with NamedTemporaryFile(suffix=metadata.suffix, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                streamed = stream_to_file(
                    chunks,
                    cast(BinaryIO, temporary),
                    self._settings.max_upload_mb * 1024 * 1024,
                )
            validate_file_signature(
                temporary_path,
                metadata.file_format,
                max_uncompressed_bytes=self._settings.max_upload_mb * 1024 * 1024 * 20,
            )
            inspection = inspect_dataset(
                temporary_path,
                metadata.file_format,
                max_rows=self._settings.max_rows,
                max_columns=self._settings.max_columns,
                preview_rows=self._settings.dataset_preview_rows,
                preview_columns=self._settings.dataset_preview_columns,
            )
            duplicate = self._repositories.datasets.get_by_fingerprint(project_id, streamed.sha256)
            if duplicate is not None:
                self._repositories.audit_logs.record(
                    action="dataset.duplicate_detected",
                    resource_type="dataset",
                    resource_id=duplicate.id,
                    metadata={"project_id": str(project_id), "sha256": streamed.sha256},
                )
                return IngestedDataset(dataset=duplicate, inspection=None, duplicate=True)

            storage_path = f"{self._session.user_id}/{uuid4()}{metadata.suffix}"
            self._storage.upload(storage_path, temporary_path.read_bytes(), metadata.media_type)
            uploaded = True
            expires_at = datetime.now(UTC) + timedelta(days=self._settings.dataset_retention_days)
            dataset = self._repositories.datasets.register(
                project_id=project_id,
                original_filename=metadata.original_filename,
                storage_path=storage_path,
                sha256=streamed.sha256,
                size_bytes=streamed.size_bytes,
                row_count=inspection.row_count,
                column_count=inspection.column_count,
                profile={
                    "schema_columns": inspection.column_names,
                    "preview": asdict(inspection.preview),
                },
                media_type=metadata.media_type,
                file_format=metadata.file_format.value,
                retention_status="active",
                retention_expires_at=expires_at,
                source_channel=source_channel,
            )
            self._repositories.audit_logs.record(
                action="dataset.telegram_uploaded",
                resource_type="dataset",
                resource_id=dataset.id,
                metadata={
                    "project_id": str(project_id),
                    "sha256": streamed.sha256,
                    "size_bytes": streamed.size_bytes,
                },
            )
            return IngestedDataset(dataset=dataset, inspection=inspection, duplicate=False)
        except Exception:
            if uploaded and storage_path is not None:
                self._storage.delete(storage_path)
            raise
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def prepare_upload(
        self,
        *,
        project_id: UUID,
        filename: str,
        content_type: str,
    ) -> UploadIntent:
        project = self._repositories.projects.get(project_id)
        if project is None:
            raise DatasetLifecycleError("The project was not found or is not owned by this user.")
        metadata = validate_upload_metadata(filename, content_type)
        storage_path = f"{self._session.user_id}/{uuid4()}{metadata.suffix}"
        signed_url, upload_token = self._storage.create_upload_url(storage_path)
        return UploadIntent(
            project_id=project_id,
            storage_path=storage_path,
            original_filename=metadata.original_filename,
            media_type=metadata.media_type,
            file_format=metadata.file_format.value,
            signed_upload_url=signed_url,
            upload_token=upload_token,
        )

    def finalize_upload(
        self,
        *,
        project_id: UUID,
        storage_path: str,
        filename: str,
        content_type: str,
    ) -> FinalizedDataset:
        project = self._repositories.projects.get(project_id)
        if project is None:
            raise DatasetLifecycleError("The project was not found or is not owned by this user.")
        metadata = validate_upload_metadata(filename, content_type)
        self._validate_owned_object_path(storage_path, metadata)
        if self._repositories.datasets.get_by_storage_path(storage_path) is not None:
            raise DatasetLifecycleError("This uploaded object has already been finalized.")

        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(suffix=metadata.suffix, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                streamed = self._storage.download_to(
                    storage_path,
                    cast(BinaryIO, temporary),
                    self._settings.max_upload_mb * 1024 * 1024,
                )
            validate_file_signature(
                temporary_path,
                metadata.file_format,
                max_uncompressed_bytes=self._settings.max_upload_mb * 1024 * 1024 * 20,
            )
            inspection = inspect_dataset(
                temporary_path,
                metadata.file_format,
                max_rows=self._settings.max_rows,
                max_columns=self._settings.max_columns,
                preview_rows=self._settings.dataset_preview_rows,
                preview_columns=self._settings.dataset_preview_columns,
            )
            expires_at = datetime.now(UTC) + timedelta(days=self._settings.dataset_retention_days)
            trusted = create_service_repositories(self._settings, self._session.user_id)
            dataset = trusted.datasets.register(
                project_id=project_id,
                original_filename=metadata.original_filename,
                storage_path=storage_path,
                sha256=streamed.sha256,
                size_bytes=streamed.size_bytes,
                row_count=inspection.row_count,
                column_count=inspection.column_count,
                profile={
                    "schema_columns": inspection.column_names,
                    "preview": asdict(inspection.preview),
                },
                media_type=metadata.media_type,
                file_format=metadata.file_format.value,
                retention_status="active",
                retention_expires_at=expires_at,
                source_channel="web",
            )
            return FinalizedDataset(dataset=dataset, inspection=inspection)
        except Exception:
            self._storage.delete(storage_path)
            raise
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def delete_dataset(self, dataset_id: UUID) -> None:
        dataset = self._repositories.datasets.get(dataset_id)
        if dataset is None:
            raise DatasetLifecycleError("The dataset was not found or is not owned by this user.")
        trusted = create_service_repositories(self._settings, self._session.user_id)
        trusted.datasets.set_retention_status(dataset_id, "deletion_pending")
        try:
            self._storage.delete(dataset.storage_path)
        except Exception:
            trusted.datasets.set_retention_status(dataset_id, "active")
            raise

        audit_metadata = {
            "project_id": str(dataset.project_id),
            "storage_path": dataset.storage_path,
            "sha256": dataset.sha256,
            "size_bytes": dataset.size_bytes,
        }
        trusted.audit_logs.record(
            action="dataset.deletion_started",
            resource_type="dataset",
            resource_id=dataset.id,
            metadata=audit_metadata,
        )
        trusted.datasets.delete(dataset.id)
        trusted.audit_logs.record(
            action="dataset.deleted",
            resource_type="dataset",
            resource_id=dataset.id,
            metadata=audit_metadata,
        )

    def _validate_owned_object_path(self, storage_path: str, metadata: UploadMetadata) -> None:
        parts = storage_path.split("/")
        if len(parts) != 2 or parts[0] != str(self._session.user_id):
            raise DatasetLifecycleError("The storage path is not owned by this user.")
        object_name = Path(parts[1])
        if object_name.suffix.lower() != metadata.suffix:
            raise DatasetLifecycleError("The storage object extension does not match the upload.")
        try:
            UUID(object_name.stem)
        except ValueError as exc:
            raise DatasetLifecycleError(
                "The storage object name is not a server-issued UUID."
            ) from exc

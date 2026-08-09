from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from zubepredict_core.datasets.files import DatasetFileError, stream_to_file
from zubepredict_core.datasets.lifecycle import DatasetLifecycleService
from zubepredict_core.repositories.models import DatasetRecord, ProjectRecord
from zubepredict_core.repositories.supabase import AuthenticatedSupabaseSession
from zubepredict_core.shared.config import Settings


class FakeStorage:
    def __init__(self, content: bytes = b"target,value\n0,10\n1,20\n") -> None:
        self.content = content
        self.deleted: list[str] = []

    def create_upload_url(self, path: str) -> tuple[str, str]:
        return f"https://storage.invalid/upload/{path}", "short-lived-token"

    def download_to(self, path: str, destination, max_bytes: int):
        midpoint = max(len(self.content) // 2, 1)
        return stream_to_file(
            [self.content[:midpoint], self.content[midpoint:]], destination, max_bytes
        )

    def delete(self, path: str) -> None:
        self.deleted.append(path)


class FakeProjectRepository:
    def __init__(self, project: ProjectRecord) -> None:
        self.project = project

    def get(self, project_id: UUID) -> ProjectRecord | None:
        return self.project if project_id == self.project.id else None


class FakeDatasetRepository:
    def __init__(self, owner_id: UUID) -> None:
        self.owner_id = owner_id
        self.records: dict[UUID, DatasetRecord] = {}
        self.statuses: list[str] = []

    def get(self, dataset_id: UUID) -> DatasetRecord | None:
        return self.records.get(dataset_id)

    def get_by_storage_path(self, storage_path: str) -> DatasetRecord | None:
        return next(
            (record for record in self.records.values() if record.storage_path == storage_path),
            None,
        )

    def register(self, **payload: Any) -> DatasetRecord:
        dataset = DatasetRecord(
            id=uuid4(),
            owner_id=self.owner_id,
            created_at="2026-08-09T00:00:00+00:00",
            validated_at="2026-08-09T00:00:00+00:00",
            **payload,
        )
        self.records[dataset.id] = dataset
        return dataset

    def set_retention_status(self, dataset_id: UUID, status: str) -> DatasetRecord:
        self.statuses.append(status)
        record = self.records[dataset_id].model_copy(update={"retention_status": status})
        self.records[dataset_id] = record
        return record

    def delete(self, dataset_id: UUID) -> None:
        self.records.pop(dataset_id)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, **event: Any) -> SimpleNamespace:
        self.events.append(event)
        return SimpleNamespace(id=1, **event)


@dataclass
class RepositoryBundle:
    projects: FakeProjectRepository
    datasets: FakeDatasetRepository
    audit_logs: FakeAuditRepository


def lifecycle(monkeypatch, *, content: bytes = b"target,value\n0,10\n1,20\n"):
    owner_id = uuid4()
    project = ProjectRecord(id=uuid4(), owner_id=owner_id, name="Owned project")
    datasets = FakeDatasetRepository(owner_id)
    audit = FakeAuditRepository()
    repositories = RepositoryBundle(FakeProjectRepository(project), datasets, audit)
    trusted = RepositoryBundle(FakeProjectRepository(project), datasets, audit)
    monkeypatch.setattr(
        "zubepredict_core.datasets.lifecycle.create_service_repositories",
        lambda settings, requested_owner: trusted,
    )
    storage = FakeStorage(content)
    service = DatasetLifecycleService(
        Settings(
            _env_file=None,
            max_upload_mb=1,
            max_rows=100,
            max_columns=10,
            dataset_preview_rows=1,
            dataset_preview_columns=1,
        ),
        AuthenticatedSupabaseSession(client=SimpleNamespace(), user_id=owner_id),  # type: ignore[arg-type]
        repositories,  # type: ignore[arg-type]
        storage,
    )
    return service, project, datasets, audit, storage


def test_prepare_uses_owned_uuid_path(monkeypatch) -> None:
    service, project, _, _, _ = lifecycle(monkeypatch)

    intent = service.prepare_upload(
        project_id=project.id,
        filename="sales.csv",
        content_type="text/csv",
    )

    owner, object_name = intent.storage_path.split("/")
    assert UUID(owner) == project.owner_id
    assert UUID(object_name.removesuffix(".csv"))
    assert intent.signed_upload_url.startswith("https://")
    assert intent.upload_token == "short-lived-token"


def test_finalize_hashes_validates_previews_and_registers(monkeypatch) -> None:
    service, project, datasets, _, storage = lifecycle(monkeypatch)
    intent = service.prepare_upload(
        project_id=project.id,
        filename="sales.csv",
        content_type="text/csv",
    )

    finalized = service.finalize_upload(
        project_id=project.id,
        storage_path=intent.storage_path,
        filename=intent.original_filename,
        content_type=intent.media_type,
    )

    assert finalized.dataset.id in datasets.records
    assert len(finalized.dataset.sha256) == 64
    assert finalized.inspection.row_count == 2
    assert len(finalized.inspection.preview.rows) == 1
    assert storage.deleted == []


def test_invalid_or_oversized_content_is_removed(monkeypatch) -> None:
    service, project, datasets, _, storage = lifecycle(monkeypatch, content=b"PK\x03\x04binary")
    intent = service.prepare_upload(
        project_id=project.id,
        filename="fake.csv",
        content_type="text/csv",
    )

    with pytest.raises(DatasetFileError, match="binary"):
        service.finalize_upload(
            project_id=project.id,
            storage_path=intent.storage_path,
            filename=intent.original_filename,
            content_type=intent.media_type,
        )

    assert not datasets.records
    assert storage.deleted == [intent.storage_path]


def test_owned_delete_is_retained_in_audit_log(monkeypatch) -> None:
    service, project, datasets, audit, storage = lifecycle(monkeypatch)
    intent = service.prepare_upload(
        project_id=project.id,
        filename="sales.csv",
        content_type="text/csv",
    )
    finalized = service.finalize_upload(
        project_id=project.id,
        storage_path=intent.storage_path,
        filename=intent.original_filename,
        content_type=intent.media_type,
    )

    service.delete_dataset(finalized.dataset.id)

    assert datasets.statuses == ["deletion_pending"]
    assert finalized.dataset.id not in datasets.records
    assert storage.deleted == [intent.storage_path]
    assert [event["action"] for event in audit.events] == [
        "dataset.deletion_started",
        "dataset.deleted",
    ]

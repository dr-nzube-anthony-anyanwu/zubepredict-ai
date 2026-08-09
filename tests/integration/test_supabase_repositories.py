from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from zubepredict_core.repositories import supabase as supabase_module
from zubepredict_core.repositories.supabase import (
    AuthenticatedSupabaseSession,
    SupabaseConfigurationError,
    SupabaseProjectRepository,
    SupabaseRepositorySet,
    create_authenticated_repositories,
)
from zubepredict_core.shared.config import Settings


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeQuery:
    def __init__(self, client: FakeClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload: dict[str, Any] | None = None
        self.filters: list[tuple[str, Any]] = []
        self.row_limit: int | None = None
        self.descending = False

    def select(self, _columns: str) -> FakeQuery:
        self.operation = "select"
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self.operation = "insert"
        self.payload = payload
        return self

    def delete(self) -> FakeQuery:
        self.operation = "delete"
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append((column, value))
        return self

    def limit(self, value: int) -> FakeQuery:
        self.row_limit = value
        return self

    def order(self, _column: str, *, desc: bool = False) -> FakeQuery:
        self.descending = desc
        return self

    def execute(self) -> FakeResponse:
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.operation == "insert":
            inserted = {
                "id": len(rows) + 1 if self.table_name == "audit_logs" else str(uuid4()),
                "created_at": "2026-08-09T00:00:00+00:00",
                "updated_at": "2026-08-09T00:00:00+00:00",
                **(self.payload or {}),
            }
            rows.append(inserted)
            return FakeResponse([inserted.copy()])

        matched = [
            row
            for row in rows
            if all(str(row.get(column)) == str(value) for column, value in self.filters)
        ]
        if self.operation == "delete":
            self.client.tables[self.table_name] = [row for row in rows if row not in matched]
            return FakeResponse([row.copy() for row in matched])
        if self.operation == "update":
            for row in matched:
                row.update(self.payload or {})
            return FakeResponse([row.copy() for row in matched])

        if self.descending:
            matched.reverse()
        if self.row_limit is not None:
            matched = matched[: self.row_limit]
        return FakeResponse([row.copy() for row in matched])


class FakeAuth:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id

    def get_user(self, _access_token: str) -> SimpleNamespace:
        return SimpleNamespace(user=SimpleNamespace(id=str(self.user_id)))


class FakeClient:
    def __init__(
        self,
        tables: dict[str, list[dict[str, Any]]] | None = None,
        user_id: UUID | None = None,
    ) -> None:
        self.tables = tables if tables is not None else {}
        self.auth = FakeAuth(user_id or uuid4())

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)


def project_row(project_id: UUID, owner_id: UUID, name: str) -> dict[str, Any]:
    return {
        "id": str(project_id),
        "owner_id": str(owner_id),
        "name": name,
        "description": None,
        "created_at": "2026-08-09T00:00:00+00:00",
        "updated_at": "2026-08-09T00:00:00+00:00",
    }


def test_owned_repository_filters_cross_user_rows_and_writes_owner() -> None:
    user_a = uuid4()
    user_b = uuid4()
    project_a = uuid4()
    project_b = uuid4()
    shared_tables = {
        "projects": [
            project_row(project_a, user_a, "A project"),
            project_row(project_b, user_b, "B project"),
        ]
    }
    client = FakeClient(shared_tables)
    repository = SupabaseProjectRepository(
        AuthenticatedSupabaseSession(client=client, user_id=user_a)  # type: ignore[arg-type]
    )

    assert [project.id for project in repository.list()] == [project_a]
    assert repository.get(project_b) is None

    created = repository.create(name="New project")
    assert created.owner_id == user_a
    created_row = next(row for row in shared_tables["projects"] if row["id"] == str(created.id))
    assert created_row["owner_id"] == str(user_a)

    repository.delete(project_b)
    assert any(row["id"] == str(project_b) for row in shared_tables["projects"])


def test_authenticated_factory_validates_token_and_sets_bearer_header(monkeypatch) -> None:
    user_id = uuid4()
    fake_client = FakeClient(user_id=user_id)
    captured: dict[str, Any] = {}

    def fake_create_client(url: str, key: str, *, options: Any) -> FakeClient:
        captured.update(url=url, key=key, options=options)
        return fake_client

    monkeypatch.setattr(supabase_module, "create_client", fake_create_client)
    settings = Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_anon_key="publishable-key",
    )

    repositories = create_authenticated_repositories(settings, "user-access-token")

    assert repositories.projects._owner_id == user_id
    assert captured["options"].headers["Authorization"] == "Bearer user-access-token"
    assert captured["options"].persist_session is False


def test_authenticated_factory_requires_configuration() -> None:
    with pytest.raises(SupabaseConfigurationError, match="SUPABASE_URL"):
        create_authenticated_repositories(Settings(_env_file=None), "token")


def test_all_repository_types_scope_reads_to_owner() -> None:
    user_a = uuid4()
    user_b = uuid4()
    project_id = uuid4()
    dataset_id = uuid4()
    experiment_id = uuid4()
    run_id = uuid4()
    report_id = uuid4()
    created_at = "2026-08-09T00:00:00+00:00"
    tables = {
        "datasets": [
            {
                "id": str(dataset_id),
                "owner_id": str(user_a),
                "project_id": str(project_id),
                "original_filename": "data.csv",
                "storage_path": f"{user_a}/data.csv",
                "sha256": "a" * 64,
                "size_bytes": 10,
                "created_at": created_at,
            },
            {
                "id": str(uuid4()),
                "owner_id": str(user_b),
                "project_id": str(project_id),
                "original_filename": "private.csv",
                "storage_path": f"{user_b}/private.csv",
                "sha256": "b" * 64,
                "size_bytes": 10,
                "created_at": created_at,
            },
        ],
        "experiments": [
            {
                "id": str(experiment_id),
                "owner_id": str(user_a),
                "project_id": str(project_id),
                "dataset_id": str(dataset_id),
                "created_at": created_at,
            }
        ],
        "model_runs": [
            {
                "id": str(run_id),
                "owner_id": str(user_a),
                "experiment_id": str(experiment_id),
                "model_name": "Baseline",
                "created_at": created_at,
            }
        ],
        "reports": [
            {
                "id": str(report_id),
                "owner_id": str(user_a),
                "experiment_id": str(experiment_id),
                "report_type": "html",
                "storage_path": f"{user_a}/report.html",
                "created_at": created_at,
            }
        ],
    }
    repositories = SupabaseRepositorySet.from_session(
        AuthenticatedSupabaseSession(
            client=FakeClient(tables),  # type: ignore[arg-type]
            user_id=user_a,
        )
    )

    assert [row.id for row in repositories.datasets.list_for_project(project_id)] == [dataset_id]
    assert [row.id for row in repositories.experiments.list_for_project(project_id)] == [
        experiment_id
    ]
    assert [row.id for row in repositories.model_runs.list_for_experiment(experiment_id)] == [
        run_id
    ]
    assert [row.id for row in repositories.reports.list_for_experiment(experiment_id)] == [
        report_id
    ]


def test_trusted_writer_methods_stamp_owner_id() -> None:
    owner_id = uuid4()
    experiment_id = uuid4()
    repositories = SupabaseRepositorySet.from_session(
        AuthenticatedSupabaseSession(
            client=FakeClient(),  # type: ignore[arg-type]
            user_id=owner_id,
        )
    )

    run = repositories.model_runs.record(
        experiment_id=experiment_id,
        model_name="Baseline",
        metrics={"f1_macro": 0.5},
        status="completed",
    )
    report = repositories.reports.create(
        experiment_id=experiment_id,
        report_type="html",
        storage_path=f"{owner_id}/report.html",
    )

    assert run.owner_id == owner_id
    assert report.owner_id == owner_id


def test_decision_update_uses_optimistic_version_and_owner_filter() -> None:
    owner_id = uuid4()
    project_id = uuid4()
    dataset_id = uuid4()
    experiment_id = uuid4()
    created_at = "2026-08-09T00:00:00+00:00"
    tables = {
        "experiments": [
            {
                "id": str(experiment_id),
                "owner_id": str(owner_id),
                "project_id": str(project_id),
                "dataset_id": str(dataset_id),
                "decision_version": 1,
                "created_at": created_at,
            }
        ]
    }
    repositories = SupabaseRepositorySet.from_session(
        AuthenticatedSupabaseSession(
            client=FakeClient(tables),  # type: ignore[arg-type]
            user_id=owner_id,
        )
    )

    updated = repositories.experiments.update_decision(
        experiment_id,
        expected_version=1,
        detected_task="regression",
        target_column="price",
        task_confidence=0.9,
        decision_evidence={"reason": "numeric target"},
        decision_source="deterministic",
    )

    assert updated.decision_version == 2
    assert updated.detected_task == "regression"
    with pytest.raises(supabase_module.SupabaseRepositoryError, match="concurrently"):
        repositories.experiments.update_decision(
            experiment_id,
            expected_version=1,
            detected_task="binary_classification",
            target_column="churn",
            task_confidence=1.0,
            decision_evidence={},
            decision_source="user_override",
        )


def test_audit_history_is_scoped_to_owner_and_resource() -> None:
    owner_id = uuid4()
    other_owner = uuid4()
    experiment_id = uuid4()
    other_experiment = uuid4()
    created_at = "2026-08-09T00:00:00+00:00"
    tables = {
        "audit_logs": [
            {
                "id": 1,
                "owner_id": str(owner_id),
                "action": "experiment.task_override_applied",
                "resource_type": "experiment",
                "resource_id": str(experiment_id),
                "metadata": {},
                "created_at": created_at,
            },
            {
                "id": 2,
                "owner_id": str(other_owner),
                "action": "experiment.task_override_applied",
                "resource_type": "experiment",
                "resource_id": str(experiment_id),
                "metadata": {},
                "created_at": created_at,
            },
            {
                "id": 3,
                "owner_id": str(owner_id),
                "action": "experiment.task_override_applied",
                "resource_type": "experiment",
                "resource_id": str(other_experiment),
                "metadata": {},
                "created_at": created_at,
            },
        ]
    }
    repositories = SupabaseRepositorySet.from_session(
        AuthenticatedSupabaseSession(
            client=FakeClient(tables),  # type: ignore[arg-type]
            user_id=owner_id,
        )
    )

    events = repositories.audit_logs.list_for_resource(
        resource_type="experiment", resource_id=experiment_id
    )

    assert [event.id for event in events] == [1]

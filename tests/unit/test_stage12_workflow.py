from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from zubepredict_api.routes import experiments as experiment_routes
from zubepredict_core.ml_engine.tournament import TournamentCancelled
from zubepredict_core.repositories.models import ExperimentRecord
from zubepredict_core.shared.schemas import TaskDecision, TaskType
from zubepredict_core.workflows import (
    SupabaseCheckpointSaver,
    build_experiment_graph,
    run_experiment_graph,
)
from zubepredict_core.workflows.experiment import WorkflowTransientError


class WorkflowContext:
    def __init__(self, *, ambiguous: bool = False, transient_profile: bool = False) -> None:
        self.ambiguous = ambiguous
        self.transient_profile = transient_profile
        self.profile_calls = 0
        self.training_calls = 0
        self.finalize_calls = 0
        self.cancelled = False

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise TournamentCancelled("cancelled")

    def progress(self, phase: str, value: int, message: str) -> None:
        del phase, value, message

    def profile(self) -> dict[str, Any]:
        self.profile_calls += 1
        if self.transient_profile and self.profile_calls == 1:
            raise WorkflowTransientError("retry me")
        return {"row_count": 10, "columns": ["feature", "target"]}

    def decide(
        self,
        configuration: dict[str, Any],
        task_override: dict[str, Any] | None,
    ) -> TaskDecision:
        del configuration
        if self.ambiguous and task_override is None:
            return TaskDecision(
                task_type=TaskType.NEEDS_CLARIFICATION,
                confidence=0.4,
                reasons=["Ambiguous test fixture."],
                requires_clarification=True,
                clarification_question="Confirm the task and target.",
            )
        return TaskDecision(
            task_type=TaskType.REGRESSION,
            target_column="target",
            confidence=1,
            reasons=["Deterministic test fixture."],
            decision_source="user_override" if task_override else "deterministic",
        )

    def validate_plan(
        self, decision: TaskDecision, configuration: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        del configuration
        return {"task_type": decision.task_type.value}, None

    def train_and_persist(
        self, decision: TaskDecision, configuration: dict[str, Any]
    ) -> dict[str, Any]:
        del decision, configuration
        self.training_calls += 1
        return {"winner_model": "deterministic-model"}

    def finalize(self, result: dict[str, Any]) -> dict[str, Any]:
        self.finalize_calls += 1
        return result


class CheckpointQuery:
    def __init__(self, client: CheckpointClient, table: str, operation: str) -> None:
        self.client = client
        self.table = table
        self.operation = operation
        self.payload: Any = None
        self.filters: list[tuple[str, Any]] = []
        self.ordering: tuple[str, bool] | None = None
        self.row_limit: int | None = None

    def select(self, columns: str) -> CheckpointQuery:
        del columns
        self.operation = "select"
        return self

    def upsert(self, payload: Any, on_conflict: str) -> CheckpointQuery:
        del on_conflict
        self.operation = "upsert"
        self.payload = payload
        return self

    def eq(self, field: str, value: Any) -> CheckpointQuery:
        self.filters.append((field, value))
        return self

    def lt(self, field: str, value: Any) -> CheckpointQuery:
        self.filters.append((f"lt:{field}", value))
        return self

    def order(self, field: str, desc: bool = False) -> CheckpointQuery:
        self.ordering = (field, desc)
        return self

    def limit(self, value: int) -> CheckpointQuery:
        self.row_limit = value
        return self

    def execute(self) -> Any:
        rows = self.client.rows.setdefault(self.table, [])
        if self.operation == "upsert":
            incoming = self.payload if isinstance(self.payload, list) else [self.payload]
            for item in incoming:
                row = dict(item)
                row.setdefault("created_at", self.client.sequence)
                self.client.sequence += 1
                identity = tuple(
                    row.get(key)
                    for key in (
                        "owner_id",
                        "thread_id",
                        "checkpoint_ns",
                        "checkpoint_id",
                        "task_id",
                        "write_index",
                    )
                )
                rows[:] = [
                    existing
                    for existing in rows
                    if tuple(existing.get(key) for key in (
                        "owner_id",
                        "thread_id",
                        "checkpoint_ns",
                        "checkpoint_id",
                        "task_id",
                        "write_index",
                    ))
                    != identity
                ]
                rows.append(row)
            return SimpleNamespace(data=incoming)
        selected = list(rows)
        for field, value in self.filters:
            if field.startswith("lt:"):
                selected = [item for item in selected if item[field[3:]] < value]
            else:
                selected = [item for item in selected if item.get(field) == value]
        if self.ordering:
            field, descending = self.ordering
            selected.sort(key=lambda item: item[field], reverse=descending)
        if self.row_limit is not None:
            selected = selected[: self.row_limit]
        return SimpleNamespace(data=selected)


class CheckpointClient:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.sequence = 0

    def table(self, name: str) -> CheckpointQuery:
        return CheckpointQuery(self, name, "table")


def _state() -> dict[str, Any]:
    return {
        "experiment_id": str(uuid4()),
        "owner_id": str(uuid4()),
        "job_id": str(uuid4()),
        "phase": "queued",
        "configuration": {},
        "completed": False,
    }


def test_graph_interrupts_and_resumes_the_same_thread() -> None:
    context = WorkflowContext(ambiguous=True)
    graph = build_experiment_graph(context, MemorySaver())
    initial = _state()
    thread_id = initial["experiment_id"]

    interrupted = run_experiment_graph(graph, initial, thread_id=thread_id)
    assert interrupted.interrupted is True
    assert interrupted.clarification["kind"] == "task_decision"
    assert context.training_calls == 0

    completed = run_experiment_graph(
        graph,
        initial,
        thread_id=thread_id,
        resume_payload={
            "task_type": "regression",
            "target_column": "target",
            "confirmed_by_user": True,
        },
    )
    assert completed.state["completed"] is True
    assert context.training_calls == 1


def test_completed_checkpoint_does_not_duplicate_training() -> None:
    context = WorkflowContext()
    graph = build_experiment_graph(context, MemorySaver())
    initial = _state()
    thread_id = initial["experiment_id"]

    run_experiment_graph(graph, initial, thread_id=thread_id)
    run_experiment_graph(graph, initial, thread_id=thread_id)

    assert context.training_calls == 1
    assert context.finalize_calls == 1


def test_supabase_checkpoints_survive_a_new_worker_without_retraining() -> None:
    owner_id = uuid4()
    client = CheckpointClient()
    first_context = WorkflowContext()
    initial = _state()
    thread_id = initial["experiment_id"]
    first_graph = build_experiment_graph(
        first_context, SupabaseCheckpointSaver(client, owner_id)  # type: ignore[arg-type]
    )
    run_experiment_graph(first_graph, initial, thread_id=thread_id)

    replacement_context = WorkflowContext()
    replacement_graph = build_experiment_graph(
        replacement_context,
        SupabaseCheckpointSaver(client, owner_id),  # type: ignore[arg-type]
    )
    result = run_experiment_graph(replacement_graph, initial, thread_id=thread_id)

    assert result.state["completed"] is True
    assert first_context.training_calls == 1
    assert replacement_context.training_calls == 0
    assert client.rows["workflow_checkpoints"]


def test_pre_training_transient_failure_retries_but_cancellation_stops() -> None:
    retrying = WorkflowContext(transient_profile=True)
    graph = build_experiment_graph(retrying, MemorySaver())
    initial = _state()
    result = run_experiment_graph(graph, initial, thread_id=initial["experiment_id"])
    assert result.state["completed"] is True
    assert retrying.profile_calls == 2

    cancelled = WorkflowContext()
    cancelled.cancelled = True
    cancelled_graph = build_experiment_graph(cancelled, MemorySaver())
    cancelled_state = _state()
    with pytest.raises(TournamentCancelled):
        run_experiment_graph(
            cancelled_graph,
            cancelled_state,
            thread_id=cancelled_state["experiment_id"],
        )
    assert cancelled.training_calls == 0


def test_resume_api_requeues_the_same_job_and_thread(monkeypatch) -> None:
    owner_id, project_id, dataset_id, experiment_id, job_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    record = ExperimentRecord(
        id=experiment_id,
        owner_id=owner_id,
        project_id=project_id,
        dataset_id=dataset_id,
        job_id=job_id,
        status="needs_clarification",
        configuration={},
        created_at=datetime.now(UTC),
    )
    captured: dict[str, Any] = {}

    class Experiments:
        def get(self, value: Any) -> ExperimentRecord:
            del value
            return record

        def resume_job(self, value: Any, same_job: Any, **fields: Any) -> ExperimentRecord:
            captured.update(experiment_id=value, job_id=same_job, **fields)
            return record.model_copy(update={"status": "queued"})

    repositories = SimpleNamespace(experiments=Experiments())
    monkeypatch.setattr(
        experiment_routes.SupabaseRepositorySet,
        "from_session",
        lambda session: repositories,
    )
    monkeypatch.setattr(
        experiment_routes, "create_service_repositories", lambda *args: repositories
    )
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        experiment_routes.run_experiment, "send", lambda *args: sent.append(args)
    )

    response = experiment_routes.resume_job(
        experiment_id,
        experiment_routes.ExperimentResumeRequest(configuration={"forecast_horizon": 7}),
        SimpleNamespace(user_id=owner_id),
    )

    assert response.status == "queued"
    assert captured["job_id"] == job_id
    assert sent == [(str(experiment_id), str(owner_id), str(job_id))]


def test_stage12_migration_keeps_checkpoint_state_server_only() -> None:
    migration = next(
        Path("infrastructure/supabase/supabase/migrations").glob(
            "*_langgraph_workflow_checkpoints.sql"
        )
    ).read_text().lower()

    assert "create table if not exists public.workflow_checkpoints" in migration
    assert "create table if not exists public.workflow_checkpoint_writes" in migration
    assert "enable row level security" in migration
    assert "revoke all on public.workflow_checkpoints from anon, authenticated" in migration
    assert "grant all on public.workflow_checkpoints to service_role" in migration

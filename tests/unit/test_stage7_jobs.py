from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import Response
from zubepredict_api.routes import experiments as experiment_routes
from zubepredict_core.ml_engine.tournament import (
    TournamentCancelled,
    run_supervised_tournament,
)
from zubepredict_core.repositories.models import ExperimentRecord
from zubepredict_core.repositories.supabase import SupabaseRepositoryError
from zubepredict_core.shared.schemas import TaskDecision, TaskType

from apps.worker.tasks import _execute_tournament, _should_retry, run_experiment


def test_queue_actor_accepts_identifiers_only() -> None:
    parameters = list(inspect.signature(run_experiment.fn).parameters)

    assert parameters == ["experiment_id", "owner_id", "job_id"]
    assert run_experiment.options["max_retries"] == 2
    assert run_experiment.options["notify_shutdown"] is True
    assert run_experiment.options["on_retry_exhausted"] == "experiment_retries_exhausted"


def test_retry_policy_is_transient_and_bounded() -> None:
    assert _should_retry(0, ConnectionError("temporary")) is True
    assert _should_retry(2, ConnectionError("temporary")) is False
    assert _should_retry(0, SupabaseRepositoryError("temporary")) is True
    assert _should_retry(0, ValueError("invalid dataset")) is False


def test_worker_routes_clustering_to_stage8_without_changing_queue_contract(
    monkeypatch, tmp_path
) -> None:
    from zubepredict_core.ml_engine import unsupervised

    captured: dict[str, object] = {}

    def fake_tournament(dataframe, task_decision, **options):
        captured.update(dataframe=dataframe, decision=task_decision, options=options)
        return "stage8-result"

    monkeypatch.setattr(unsupervised, "run_unsupervised_tournament", fake_tournament)
    dataframe = pd.DataFrame({"x": range(20), "y": [index % 3 for index in range(20)]})
    task_decision = TaskDecision(
        task_type=TaskType.CLUSTERING,
        confidence=1,
        reasons=["test"],
    )

    result = _execute_tournament(
        dataframe,
        task_decision,
        {},
        tmp_path / "unused.skops",
        lambda value, label: None,
        lambda: False,
    )

    assert result == "stage8-result"
    assert captured["dataframe"] is dataframe
    assert captured["decision"] is task_decision
    assert captured["options"]["contamination"] == 0.05


def test_worker_routes_forecasting_to_stage9_with_confirmed_configuration(
    monkeypatch, tmp_path
) -> None:
    from zubepredict_core.ml_engine import forecasting

    captured: dict[str, object] = {}

    def fake_tournament(dataframe, task_decision, configuration, **options):
        captured.update(
            dataframe=dataframe,
            decision=task_decision,
            configuration=configuration,
            options=options,
        )
        return "stage9-result"

    monkeypatch.setattr(forecasting, "run_forecasting_tournament", fake_tournament)
    dataframe = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=30, freq="D"),
            "demand": range(30),
        }
    )
    task_decision = TaskDecision(
        task_type=TaskType.TIME_SERIES_FORECASTING,
        target_column="demand",
        confidence=1,
        reasons=["test"],
    )
    configuration = {"time_column": "date", "frequency": "D", "forecast_horizon": 3}

    result = _execute_tournament(
        dataframe,
        task_decision,
        configuration,
        tmp_path / "unused.skops",
        lambda value, label: None,
        lambda: False,
    )

    assert result == "stage9-result"
    assert captured["configuration"] is configuration
    assert captured["options"]["max_horizon"] >= 3


def test_worker_routes_stage10_tuning_budgets_without_changing_queue_contract(
    monkeypatch, tmp_path
) -> None:
    from zubepredict_core.ml_engine import tournament

    captured: dict[str, object] = {}

    def fake_tournament(dataframe, task_decision, **options):
        captured.update(dataframe=dataframe, decision=task_decision, options=options)
        return "stage10-result"

    monkeypatch.setattr(tournament, "run_supervised_tournament", fake_tournament)
    dataframe = pd.DataFrame({"signal": range(20), "target": range(20)})
    task_decision = TaskDecision(
        task_type=TaskType.REGRESSION,
        target_column="target",
        confidence=1,
        reasons=["test"],
    )

    result = _execute_tournament(
        dataframe,
        task_decision,
        {"tuning_enabled": True, "tuning_trials": 4, "tuning_timeout_seconds": 45},
        tmp_path / "winner.skops",
        lambda value, label: None,
        lambda: False,
    )

    assert result == "stage10-result"
    assert captured["options"]["tuning_enabled"] is True
    assert captured["options"]["tuning_trials"] == 4
    assert captured["options"]["tuning_timeout_seconds"] == 45
    assert captured["options"]["experiment_tuning_trial_limit"] >= 4
    assert captured["options"]["explanations_enabled"] is True
    assert captured["options"]["explanation_max_sample_rows"] > 0


def test_worker_rejects_invalid_stage10_budget_configuration(tmp_path) -> None:
    dataframe = pd.DataFrame({"signal": range(20), "target": range(20)})
    task_decision = TaskDecision(
        task_type=TaskType.REGRESSION,
        target_column="target",
        confidence=1,
        reasons=["test"],
    )

    with pytest.raises(ValueError, match="tuning_trials must be a positive integer"):
        _execute_tournament(
            dataframe,
            task_decision,
            {"tuning_trials": "unbounded"},
            tmp_path / "winner.skops",
            lambda value, label: None,
            lambda: False,
        )


def test_api_enqueues_only_identifiers_and_reuses_idempotency_key(monkeypatch) -> None:
    owner_id, project_id, dataset_id = uuid4(), uuid4(), uuid4()
    sent: list[tuple[str, str, str]] = []
    stored: dict[str, ExperimentRecord] = {}

    class FakeExperimentRepository:
        def get_by_idempotency_key(self, key: str) -> ExperimentRecord | None:
            return stored.get(key)

        def create_job(self, **values: object) -> ExperimentRecord:
            record = ExperimentRecord(
                id=uuid4(),
                owner_id=owner_id,
                created_at=datetime.now(UTC),
                status="queued",
                **values,
            )
            stored[str(values["idempotency_key"])] = record
            return record

    owned = SimpleNamespace(
        projects=SimpleNamespace(get=lambda value: SimpleNamespace(id=project_id)),
        datasets=SimpleNamespace(
            get=lambda value: SimpleNamespace(
                id=dataset_id, project_id=project_id, retention_status="active"
            )
        ),
    )
    trusted = SimpleNamespace(experiments=FakeExperimentRepository())
    monkeypatch.setattr(
        experiment_routes.SupabaseRepositorySet,
        "from_session",
        lambda session: owned,
    )
    monkeypatch.setattr(experiment_routes, "create_service_repositories", lambda *args: trusted)
    monkeypatch.setattr(experiment_routes.run_experiment, "send", lambda *args: sent.append(args))
    session = SimpleNamespace(user_id=owner_id)
    request = experiment_routes.ExperimentJobRequest(
        project_id=project_id,
        dataset_id=dataset_id,
        target_column="target",
    )

    first = experiment_routes.create_job(request, Response(), session, "same-request")
    second_response = Response()
    second = experiment_routes.create_job(request, second_response, session, "same-request")

    assert sent == [(str(first.id), str(owner_id), str(first.job_id))]
    assert all("\\" not in value and "/" not in value for value in sent[0])
    assert second.id == first.id
    assert second.reused is True
    assert second_response.status_code == 200


def test_tournament_honours_cancellation_before_training() -> None:
    dataframe = pd.DataFrame(
        {
            "signal": list(range(20)),
            "target": ["yes" if value % 2 else "no" for value in range(20)],
        }
    )
    decision = TaskDecision(
        task_type=TaskType.BINARY_CLASSIFICATION,
        target_column="target",
        confidence=1,
        reasons=["test"],
    )

    with pytest.raises(TournamentCancelled):
        run_supervised_tournament(
            dataframe,
            decision,
            max_models=1,
            cancellation_check=lambda: True,
        )


def test_stage7_migration_defines_durable_job_guards() -> None:
    migrations = Path("infrastructure/supabase/supabase/migrations")
    migration = next(migrations.glob("*_async_experiment_jobs.sql")).read_text().lower()

    assert "experiments_owner_idempotency_unique" in migration
    assert "experiments_job_id_unique" in migration
    assert "heartbeat_at" in migration
    assert "cancel_requested_at" in migration
    assert "grant all on public.experiments, public.model_runs to service_role" in migration
    assert "revoke update" in migration

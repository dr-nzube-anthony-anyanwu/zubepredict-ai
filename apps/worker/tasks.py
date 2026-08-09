from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, BinaryIO, cast
from uuid import UUID, uuid4

import dramatiq
import httpx
from dramatiq.middleware.shutdown import Shutdown
from redis import Redis
from zubepredict_core.data_engine.loader import load_dataframe, validate_dimensions
from zubepredict_core.data_engine.task_detector import detect_task
from zubepredict_core.datasets.files import DatasetFileFormat, validate_file_signature
from zubepredict_core.datasets.lifecycle import SupabaseDatasetObjectStorage
from zubepredict_core.ml_engine.forecasting import (
    ForecastClarificationRequired,
    prepare_forecast_contract,
)
from zubepredict_core.ml_engine.tournament import TournamentCancelled
from zubepredict_core.repositories.models import ExperimentRecord
from zubepredict_core.repositories.supabase import (
    SupabaseExperimentRepository,
    SupabaseRepositoryError,
    SupabaseRepositorySet,
    create_service_session,
)
from zubepredict_core.shared.config import get_settings
from zubepredict_core.shared.schemas import TaskDecision, TaskType
from zubepredict_core.workflows import (
    SupabaseCheckpointSaver,
    WorkflowState,
    build_experiment_graph,
    run_experiment_graph,
)

from apps.worker.broker import broker

settings = get_settings()
logger = logging.getLogger(__name__)


class _JobLock:
    def __init__(self, experiment_id: UUID) -> None:
        self._redis = Redis.from_url(settings.redis_url)
        self._key = f"zubepredict:experiment-lock:{experiment_id}"
        self._token = uuid4().hex

    def acquire(self) -> bool:
        return bool(
            self._redis.set(
                self._key,
                self._token,
                nx=True,
                ex=max(settings.job_lock_ttl_seconds, settings.training_timeout_seconds + 60),
            )
        )

    def release(self) -> None:
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
          return redis.call('del', KEYS[1])
        end
        return 0
        """
        try:
            self._redis.eval(script, 1, self._key, self._token)
        except Exception:
            # The database claim remains the durable boundary if Redis disappears.
            pass


def _repositories(owner_id: UUID) -> tuple[SupabaseRepositorySet, Any]:
    session = create_service_session(settings, owner_id)
    return SupabaseRepositorySet.from_session(session), session


def _is_cancelled(repository: SupabaseExperimentRepository, experiment_id: UUID) -> bool:
    current = repository.get(experiment_id)
    return current is None or current.cancel_requested_at is not None


def _decision(experiment: ExperimentRecord, dataframe: Any) -> TaskDecision:
    if experiment.decision_source == "user_override" and experiment.detected_task:
        return TaskDecision(
            task_type=TaskType(experiment.detected_task),
            target_column=experiment.target_column,
            confidence=experiment.task_confidence or 1.0,
            reasons=["The user-confirmed Stage 4 task decision was used."],
            evidence_hash=str(experiment.decision_evidence.get("evidence_hash", "")),
            decision_source="user_override",
        )
    return detect_task(dataframe, experiment.target_column, experiment.objective)


def _summary(
    result: Any,
    artifact_path: str | None,
    evidence_artifact_path: str | None = None,
    evidence_sha256: str | None = None,
) -> dict[str, Any]:
    excluded = {"out_of_fold_predictions", "assignments", "explanations", "error_analysis"}
    payload = cast(dict[str, Any], result.model_dump(mode="json", exclude=excluded))
    if hasattr(result, "out_of_fold_predictions"):
        payload["out_of_fold_prediction_count"] = len(result.out_of_fold_predictions)
    if hasattr(result, "assignments"):
        payload["assignment_count"] = len(result.assignments)
        payload["assignment_label_counts"] = {
            str(label): sum(1 for item in result.assignments if item.label == label)
            for label in sorted({item.label for item in result.assignments})
        }
        if artifact_path:
            payload["assignments_artifact_path"] = artifact_path
    if hasattr(result, "forecast"):
        payload["forecast_point_count"] = len(result.forecast)
        if artifact_path:
            payload["forecast_artifact_path"] = artifact_path
    if payload.get("winner_artifact"):
        payload["winner_artifact"]["path"] = artifact_path
    explanations = getattr(result, "explanations", None)
    if explanations is not None:
        payload["explanation_summary"] = {
            "method": explanations.method,
            "sampled_rows": explanations.sampled_rows,
            "background_rows": explanations.background_rows,
            "local_explanation_count": len(explanations.local_explanations),
            "top_global_features": [
                item.model_dump(mode="json") for item in explanations.global_importance[:5]
            ],
        }
    error_analysis = getattr(result, "error_analysis", None)
    if error_analysis is not None:
        payload["error_analysis_summary"] = {
            "plot_ids": [item.plot_id for item in error_analysis.plots],
            "segment_count": len(error_analysis.segments),
            "protected_columns_skipped": error_analysis.protected_columns_skipped,
        }
    if evidence_artifact_path:
        payload["evidence_artifact_path"] = evidence_artifact_path
        payload["evidence_artifact_sha256"] = evidence_sha256
    return payload


def _mark_retryable(experiment_id: UUID, owner_id: UUID, job_id: UUID, error: str) -> None:
    repositories, _ = _repositories(owner_id)
    repositories.experiments.update_job(
        experiment_id,
        job_id,
        status="queued",
        progress=0,
        error_message=error[:500],
    )


def _should_retry(retries: int, exception: BaseException) -> bool:
    return retries < settings.job_max_retries and isinstance(
        exception,
        (
            ConnectionError,
            OSError,
            TimeoutError,
            Shutdown,
            httpx.HTTPError,
            SupabaseRepositoryError,
        ),
    )


def _configuration_bool(configuration: dict[str, Any], name: str, default: bool) -> bool:
    value = configuration.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false.")
    return value


def _configuration_positive_int(configuration: dict[str, Any], name: str, default: int) -> int:
    value = configuration.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return cast(int, value)


def _execute_tournament(
    dataframe: Any,
    decision: TaskDecision,
    configuration: dict[str, Any],
    artifact_file: Path,
    progress_callback: Any,
    cancellation_check: Any,
) -> Any:
    if decision.task_type == TaskType.TIME_SERIES_FORECASTING:
        from zubepredict_core.ml_engine.forecasting import run_forecasting_tournament

        return run_forecasting_tournament(
            dataframe,
            decision,
            configuration,
            seed=settings.random_seed,
            max_horizon=settings.forecast_max_horizon,
            validation_folds=settings.forecast_validation_folds,
            max_arima_iterations=settings.forecast_max_arima_iterations,
            compute_budget_seconds=settings.training_timeout_seconds,
            progress_callback=progress_callback,
            cancellation_check=cancellation_check,
        )
    if decision.task_type in {TaskType.CLUSTERING, TaskType.ANOMALY_DETECTION}:
        from zubepredict_core.ml_engine.unsupervised import run_unsupervised_tournament

        return run_unsupervised_tournament(
            dataframe,
            decision,
            seed=settings.random_seed,
            max_candidates=max(settings.max_candidate_models, 8),
            contamination=float(configuration.get("contamination", 0.05)),
            compute_budget_seconds=settings.training_timeout_seconds,
            progress_callback=progress_callback,
            cancellation_check=cancellation_check,
        )

    from zubepredict_core.ml_engine.tournament import run_supervised_tournament

    return run_supervised_tournament(
        dataframe,
        decision,
        seed=settings.random_seed,
        max_models=settings.max_candidate_models,
        compute_budget_seconds=settings.training_timeout_seconds,
        winner_artifact_path=artifact_file,
        progress_callback=progress_callback,
        cancellation_check=cancellation_check,
        tuning_enabled=_configuration_bool(configuration, "tuning_enabled", True),
        tuning_trials=_configuration_positive_int(
            configuration, "tuning_trials", settings.max_optuna_trials
        ),
        tuning_timeout_seconds=_configuration_positive_int(
            configuration, "tuning_timeout_seconds", settings.optuna_timeout_seconds
        ),
        experiment_tuning_trial_limit=settings.max_optuna_trials,
        experiment_tuning_time_limit_seconds=settings.optuna_timeout_seconds,
        user_tuning_trial_limit=settings.user_max_optuna_trials,
        user_tuning_time_limit_seconds=settings.user_optuna_timeout_seconds,
        tuning_max_candidates=settings.tuning_max_candidates,
        explanations_enabled=_configuration_bool(configuration, "explanations_enabled", True),
        explanation_max_sample_rows=settings.explanation_max_sample_rows,
        explanation_background_rows=settings.explanation_background_rows,
        explanation_local_rows=settings.explanation_local_rows,
        explanation_max_features=settings.explanation_max_features,
        explanation_plot_sample_rows=settings.explanation_plot_sample_rows,
        explanation_learning_curve_rows=settings.explanation_learning_curve_rows,
    )


class _WorkerWorkflowContext:
    """Adapt the existing deterministic worker operations to Stage 12 graph nodes."""

    def __init__(
        self,
        repositories: SupabaseRepositorySet,
        session: Any,
        claimed: ExperimentRecord,
        temporary_directory: Path,
    ) -> None:
        if claimed.job_id is None:
            raise ValueError("A workflow experiment must have a job identifier.")
        self.repositories = repositories
        self.session = session
        self.claimed = claimed
        self.experiment_id = claimed.id
        self.owner_id = claimed.owner_id
        self.job_id = claimed.job_id
        self.temporary_directory = temporary_directory
        self._dataframe: Any | None = None

    def check_cancelled(self) -> None:
        if _is_cancelled(self.repositories.experiments, self.experiment_id):
            raise TournamentCancelled("Experiment cancellation was requested.")

    def progress(self, phase: str, value: int, message: str) -> None:
        self.repositories.experiments.update_job(
            self.experiment_id,
            self.job_id,
            status=phase,
            progress=value,
            result_summary={"current_step": message},
        )

    def _load_dataframe(self) -> Any:
        if self._dataframe is not None:
            return self._dataframe
        dataset = self.repositories.datasets.get(self.claimed.dataset_id)
        if dataset is None or dataset.project_id != self.claimed.project_id:
            raise ValueError("The experiment's owned dataset is unavailable.")
        storage = SupabaseDatasetObjectStorage(
            self.session, settings.supabase_datasets_bucket
        )
        local_dataset = self.temporary_directory / f"dataset.{dataset.file_format}"
        with local_dataset.open("wb") as handle:
            streamed = storage.download_to(
                dataset.storage_path,
                cast(BinaryIO, handle),
                settings.max_upload_mb * 1024 * 1024,
            )
        if streamed.sha256 != dataset.sha256:
            raise ValueError("The downloaded dataset checksum does not match its registry.")
        validate_file_signature(
            local_dataset,
            DatasetFileFormat(dataset.file_format),
            max_uncompressed_bytes=settings.max_upload_mb * 1024 * 1024 * 20,
        )
        dataframe = load_dataframe(local_dataset)
        validate_dimensions(dataframe, settings.max_rows, settings.max_columns)
        self._dataframe = dataframe
        return dataframe

    def profile(self) -> dict[str, Any]:
        dataframe = self._load_dataframe()
        return {
            "row_count": int(len(dataframe)),
            "column_count": int(len(dataframe.columns)),
            "columns": [str(column) for column in dataframe.columns],
        }

    def decide(
        self,
        configuration: dict[str, Any],
        task_override: dict[str, Any] | None,
    ) -> TaskDecision:
        del configuration
        dataframe = self._load_dataframe()
        if task_override is None:
            return _decision(self.claimed, dataframe)
        task_type = TaskType(str(task_override.get("task_type")))
        target = task_override.get("target_column")
        target_column = str(target).strip() if target else None
        supervised = {
            TaskType.BINARY_CLASSIFICATION,
            TaskType.MULTICLASS_CLASSIFICATION,
            TaskType.REGRESSION,
            TaskType.TIME_SERIES_FORECASTING,
        }
        if task_type in supervised and (
            target_column is None or target_column not in dataframe.columns
        ):
            raise ValueError("The confirmed task requires an existing target column.")
        if task_type in {TaskType.CLUSTERING, TaskType.ANOMALY_DETECTION} and target_column:
            raise ValueError("Unsupervised tasks do not use a target column.")
        return TaskDecision(
            task_type=task_type,
            target_column=target_column,
            confidence=1,
            reasons=["The user explicitly confirmed the clarification response."],
            decision_source="user_override",
        )

    def validate_plan(
        self,
        decision: TaskDecision,
        configuration: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        plan: dict[str, Any] = {
            "task_type": decision.task_type.value,
            "target": decision.target_column,
        }
        if decision.task_type != TaskType.TIME_SERIES_FORECASTING:
            return plan, None
        try:
            prepared = prepare_forecast_contract(
                self._load_dataframe(),
                decision,
                configuration,
                max_horizon=settings.forecast_max_horizon,
            )
        except ForecastClarificationRequired as exc:
            return plan, {
                "kind": "forecast_configuration",
                "question": str(exc),
                "required_fields": [
                    "time_column",
                    "frequency",
                    "forecast_horizon",
                    "seasonal_period",
                ],
            }
        plan["forecast_contract"] = prepared.contract.model_dump(mode="json")
        return plan, None

    def train_and_persist(
        self,
        decision: TaskDecision,
        configuration: dict[str, Any],
    ) -> dict[str, Any]:
        self.repositories.experiments.update_job(
            self.experiment_id,
            self.job_id,
            status="training",
            progress=25,
            detected_task=decision.task_type.value,
            target_column=decision.target_column,
            task_confidence=decision.confidence,
            decision_evidence=decision.model_dump(mode="json"),
            decision_source=decision.decision_source,
            error_message=None,
        )
        # A retry replaces rows for this same job instead of duplicating them.
        self.repositories.model_runs.delete_for_job(self.experiment_id, self.job_id)

        def progress(value: int, label: str) -> None:
            self.progress("training", value, label)

        artifact_file = self.temporary_directory / "winner.skops"
        result = _execute_tournament(
            self._load_dataframe(),
            decision,
            configuration,
            artifact_file,
            progress,
            lambda: _is_cancelled(self.repositories.experiments, self.experiment_id),
        )
        self.repositories.experiments.update_job(
            self.experiment_id, self.job_id, status="evaluating", progress=90
        )
        artifact_path: str | None = None
        evidence_path: str | None = None
        evidence_sha256: str | None = None
        base_path = f"{self.owner_id}/{self.experiment_id}/{self.job_id}"
        bucket = self.session.client.storage.from_(settings.supabase_artifacts_bucket)
        if getattr(result, "winner_artifact", None) is not None:
            artifact_path = f"{base_path}/winner.skops"
            bucket.upload(
                artifact_path,
                artifact_file.read_bytes(),
                {"content-type": "application/octet-stream", "upsert": "true"},
            )
        elif getattr(result, "forecast", None):
            artifact_path = f"{base_path}/forecast.json"
            forecast_bytes = json.dumps(
                {
                    "contract": result.contract.model_dump(mode="json"),
                    "winner": result.winner,
                    "forecast": [item.model_dump(mode="json") for item in result.forecast],
                },
                separators=(",", ":"),
            ).encode("utf-8")
            bucket.upload(
                artifact_path,
                forecast_bytes,
                {"content-type": "application/json", "upsert": "true"},
            )
        if getattr(result, "explanations", None) is not None:
            evidence_path = f"{base_path}/evidence.json"
            evidence_bytes = json.dumps(
                {
                    "model_name": result.winner,
                    "primary_metric": result.primary_metric,
                    "explanations": result.explanations.model_dump(mode="json"),
                    "error_analysis": result.error_analysis.model_dump(mode="json"),
                },
                separators=(",", ":"),
            ).encode("utf-8")
            evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
            bucket.upload(
                evidence_path,
                evidence_bytes,
                {"content-type": "application/json", "upsert": "true"},
            )
        elif getattr(result, "assignments", None):
            artifact_path = f"{base_path}/assignments.json"
            assignment_bytes = json.dumps(
                [item.model_dump(mode="json") for item in result.assignments],
                separators=(",", ":"),
            ).encode("utf-8")
            bucket.upload(
                artifact_path,
                assignment_bytes,
                {"content-type": "application/json", "upsert": "true"},
            )
        for score in result.leaderboard:
            metrics = {
                key: (value.model_dump(mode="json") if hasattr(value, "model_dump") else value)
                for key, value in score.metrics.items()
            }
            self.repositories.model_runs.record(
                experiment_id=self.experiment_id,
                job_id=self.job_id,
                model_name=score.model_name,
                hyperparameters=score.hyperparameters,
                metrics=metrics,
                fold_scores=[
                    fold.model_dump(mode="json")
                    for fold in getattr(score, "fold_scores", [])
                ],
                fit_seconds=score.fit_seconds,
                status=score.status,
                error_message=score.error,
                artifact_path=artifact_path if score.model_name == result.winner else None,
            )
        summary = _summary(result, artifact_path, evidence_path, evidence_sha256)
        self.repositories.experiments.update_job(
            self.experiment_id,
            self.job_id,
            status="evaluating",
            progress=95,
            winner_model=result.winner,
            primary_metric=result.primary_metric,
            warnings=result.warnings,
            result_summary=summary,
        )
        return {
            "winner_model": result.winner,
            "primary_metric": result.primary_metric,
            "warnings": result.warnings,
            "result_summary": summary,
        }

    def finalize(self, result: dict[str, Any]) -> dict[str, Any]:
        self.check_cancelled()
        self.repositories.experiments.update_job(
            self.experiment_id,
            self.job_id,
            status="completed",
            progress=100,
            winner_model=result.get("winner_model"),
            primary_metric=result.get("primary_metric"),
            warnings=result.get("warnings", []),
            result_summary=result.get("result_summary", {}),
            completed_at=datetime.now(UTC).isoformat(),
            error_message=None,
        )
        return result


@dramatiq.actor(actor_name="experiment_retries_exhausted", max_retries=0)
def experiment_retries_exhausted(message: dict[str, Any], retry_data: dict[str, Any]) -> None:
    args = message.get("args", [])
    if len(args) < 3:
        return
    experiment_id, owner_id, job_id = (UUID(str(value)) for value in args[:3])
    repositories, _ = _repositories(owner_id)
    current = repositories.experiments.get(experiment_id)
    if current is None or current.status in {"completed", "cancelled"}:
        return
    repositories.experiments.update_job(
        experiment_id,
        job_id,
        status="failed",
        progress=current.progress,
        error_message=(f"Experiment failed after {retry_data.get('retries', 0)} worker attempts."),
        completed_at=datetime.now(UTC).isoformat(),
    )


@dramatiq.actor(
    actor_name="run_experiment",
    max_retries=settings.job_max_retries,
    min_backoff=settings.job_min_backoff_ms,
    max_backoff=settings.job_max_backoff_ms,
    retry_when=_should_retry,
    on_retry_exhausted="experiment_retries_exhausted",
    notify_shutdown=True,
    time_limit=settings.training_timeout_seconds * 1000,
)
def run_experiment(experiment_id: str, owner_id: str, job_id: str) -> None:
    """Run an experiment from three identifiers; no path, data, or token crosses the queue."""

    experiment_uuid = UUID(experiment_id)
    owner_uuid = UUID(owner_id)
    job_uuid = UUID(job_id)
    lock = _JobLock(experiment_uuid)
    if not lock.acquire():
        return
    try:
        repositories, session = _repositories(owner_uuid)
        claimed = repositories.experiments.claim_job(experiment_uuid, job_uuid)
        if claimed is None:
            return
        if claimed.cancel_requested_at is not None:
            repositories.experiments.update_job(
                experiment_uuid, job_uuid, status="cancelled", progress=claimed.progress
            )
            return
        with TemporaryDirectory(prefix="zubepredict-job-") as temporary_directory:
            context = _WorkerWorkflowContext(
                repositories,
                session,
                claimed,
                Path(temporary_directory),
            )
            checkpointer = SupabaseCheckpointSaver(session.client, owner_uuid)
            graph = build_experiment_graph(context, checkpointer)
            pending_resume = claimed.result_summary.get("workflow_resume_payload")
            resume_payload = pending_resume if isinstance(pending_resume, dict) else None
            execution = run_experiment_graph(
                graph,
                WorkflowState(
                    experiment_id=experiment_id,
                    owner_id=owner_id,
                    job_id=job_id,
                    phase="queued",
                    configuration=claimed.configuration,
                    completed=False,
                ),
                thread_id=experiment_id,
                resume_payload=resume_payload,
            )
            if execution.interrupted:
                decision = execution.state.get("decision", {})
                repositories.experiments.update_job(
                    experiment_uuid,
                    job_uuid,
                    status="needs_clarification",
                    progress=24,
                    detected_task=decision.get("task_type"),
                    target_column=decision.get("target_column"),
                    task_confidence=decision.get("confidence"),
                    decision_evidence=decision,
                    error_message=(execution.clarification or {}).get("question"),
                    result_summary={
                        "workflow": {
                            "phase": "needs_clarification",
                            "thread_id": experiment_id,
                            "clarification": execution.clarification,
                        }
                    },
                )
            return
    except TournamentCancelled:
        repositories, _ = _repositories(owner_uuid)
        current = repositories.experiments.get(experiment_uuid)
        repositories.experiments.update_job(
            experiment_uuid,
            job_uuid,
            status="cancelled",
            progress=current.progress if current else 0,
            completed_at=datetime.now(UTC).isoformat(),
        )
    except Shutdown:
        _mark_retryable(experiment_uuid, owner_uuid, job_uuid, "Worker shutdown; job requeued.")
        raise
    except Exception as exc:
        _mark_retryable(experiment_uuid, owner_uuid, job_uuid, str(exc))
        raise
    finally:
        lock.release()


@dramatiq.actor(actor_name="recover_stale_experiments", max_retries=2)
def recover_stale_experiments() -> None:
    """Requeue jobs abandoned without a heartbeat, for example after worker termination."""

    system_owner = UUID(int=0)
    repositories, _ = _repositories(system_owner)
    recovered = 0
    stale_after = max(settings.job_stale_after_seconds, settings.training_timeout_seconds + 60)
    for stale in repositories.experiments.list_stale(stale_after):
        if stale.job_id is None:
            continue
        owner_repositories, _ = _repositories(stale.owner_id)
        if stale.cancel_requested_at is not None:
            owner_repositories.experiments.update_job(
                stale.id,
                stale.job_id,
                status="cancelled",
                progress=stale.progress,
                completed_at=datetime.now(UTC).isoformat(),
            )
            continue
        if not owner_repositories.experiments.recover_stale_job(stale):
            continue
        run_experiment.send(str(stale.id), str(stale.owner_id), str(stale.job_id))
        recovered += 1
    if recovered:
        logger.info("Recovered %d stale experiment job(s).", recovered)


assert broker is not None

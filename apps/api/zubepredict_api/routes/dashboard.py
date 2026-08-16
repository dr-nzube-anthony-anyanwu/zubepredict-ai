from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from zubepredict_api.routes.hermes import (
    CancelRequest,
    ClarificationAnswerRequest,
    ConstitutionConfirmationRequest,
    ConstitutionRequest,
    ReportType,
    StartExperimentRequest,
    _clarification,
    answer_clarification,
    cancel_experiment,
    confirm_constitution,
    create_constitution,
    get_experiment_evidence,
    get_report_content_response,
    get_report_reference,
    start_experiment,
)
from zubepredict_api.security.hermes import TrustedHermesPrincipal
from zubepredict_api.security.user import require_user_session
from zubepredict_core.repositories.models import ExperimentRecord
from zubepredict_core.repositories.supabase import (
    AuthenticatedSupabaseSession,
    SupabaseRepositorySet,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
UserSession = Annotated[AuthenticatedSupabaseSession, Depends(require_user_session)]


class CreateDashboardProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


def _principal(session: AuthenticatedSupabaseSession) -> TrustedHermesPrincipal:
    return TrustedHermesPrincipal(owner_id=session.user_id, key_id="supabase-auth", channel="web")


def _safe_audit_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "project_id",
        "experiment_id",
        "expires_in_seconds",
        "source_channel",
        "duplicate",
        "status",
    }
    return {key: value for key, value in metadata.items() if key in allowed}


def _experiment_payload(
    repositories: SupabaseRepositorySet, experiment: ExperimentRecord
) -> dict[str, Any]:
    model_runs = repositories.model_runs.list_for_experiment(experiment.id)
    reports = repositories.reports.list_for_experiment(experiment.id)
    audits = repositories.audit_logs.list_for_resource(
        resource_type="experiment", resource_id=experiment.id
    )
    clarification_id, clarification = _clarification(experiment)
    constitution = experiment.configuration.get("constitution", {})
    return {
        "id": str(experiment.id),
        "project_id": str(experiment.project_id),
        "dataset_id": str(experiment.dataset_id),
        "objective": experiment.objective,
        "target_column": experiment.target_column,
        "task": experiment.detected_task,
        "primary_metric": experiment.primary_metric,
        "winner_model": experiment.winner_model,
        "status": experiment.status,
        "progress": experiment.progress,
        "error_message": experiment.error_message,
        "source_channel": experiment.source_channel,
        "constitution": constitution if isinstance(constitution, dict) else {},
        "pending_clarification": (
            {
                "clarification_id": clarification_id,
                "clarification_version": experiment.state_version,
                "data": clarification,
            }
            if clarification is not None
            else None
        ),
        "result_summary": experiment.result_summary,
        "warnings": experiment.warnings,
        "created_at": experiment.created_at,
        "started_at": experiment.started_at,
        "completed_at": experiment.completed_at,
        "model_leaderboard": [
            {
                "id": str(run.id),
                "model_name": run.model_name,
                "status": run.status,
                "metrics": run.metrics,
                "fit_seconds": run.fit_seconds,
                "predict_seconds": run.predict_seconds,
            }
            for run in model_runs
        ],
        "reports": [
            {
                "id": str(report.id),
                "report_type": report.report_type,
                "report_version": report.report_version,
                "filename": report.filename,
                "content_type": report.content_type,
                "size_bytes": report.size_bytes,
                "sha256": report.sha256,
                "evidence_hash": report.evidence_hash,
                "created_at": report.created_at,
            }
            for report in reports
        ],
        "audit_history": [
            {
                "id": audit.id,
                "action": audit.action,
                "resource_type": audit.resource_type,
                "metadata": _safe_audit_metadata(audit.metadata),
                "created_at": audit.created_at,
            }
            for audit in audits
        ],
    }


@router.get("/overview")
def dashboard_overview(session: UserSession) -> dict[str, Any]:
    repositories = SupabaseRepositorySet.from_session(session)
    projects = repositories.projects.list()
    project_items: list[dict[str, Any]] = []
    all_experiments: list[dict[str, Any]] = []
    for project in projects:
        datasets = repositories.datasets.list_for_project(project.id)
        experiments = repositories.experiments.list_for_project(project.id)
        experiment_items = [_experiment_payload(repositories, item) for item in experiments]
        all_experiments.extend(experiment_items)
        project_items.append(
            {
                "id": str(project.id),
                "name": project.name,
                "description": project.description,
                "source_channel": project.source_channel,
                "created_at": project.created_at,
                "datasets": [
                    {
                        "id": str(dataset.id),
                        "project_id": str(dataset.project_id),
                        "filename": dataset.original_filename,
                        "size_bytes": dataset.size_bytes,
                        "row_count": dataset.row_count,
                        "column_count": dataset.column_count,
                        "file_format": dataset.file_format,
                        "retention_status": dataset.retention_status,
                        "source_channel": dataset.source_channel,
                        "schema_columns": (dataset.profile or {}).get("schema_columns", []),
                        "created_at": dataset.created_at,
                    }
                    for dataset in datasets
                ],
                "experiment_ids": [item["id"] for item in experiment_items],
            }
        )
    statuses: dict[str, int] = {}
    for experiment in all_experiments:
        value = str(experiment["status"])
        statuses[value] = statuses.get(value, 0) + 1
    return {
        "projects": project_items,
        "experiments": all_experiments,
        "summary": {
            "project_count": len(project_items),
            "dataset_count": sum(len(item["datasets"]) for item in project_items),
            "experiment_count": len(all_experiments),
            "statuses": statuses,
        },
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_dashboard_project(
    request: CreateDashboardProjectRequest, session: UserSession
) -> dict[str, Any]:
    project = SupabaseRepositorySet.from_session(session).projects.create(
        name=request.name.strip(), description=request.description, source_channel="web"
    )
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "source_channel": project.source_channel,
    }


@router.get("/experiments/{experiment_id}")
def dashboard_experiment(experiment_id: UUID, session: UserSession) -> dict[str, Any]:
    repositories = SupabaseRepositorySet.from_session(session)
    experiment = repositories.experiments.get(experiment_id)
    if experiment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The experiment was not found.")
    return _experiment_payload(repositories, experiment)


@router.post("/constitutions", status_code=status.HTTP_201_CREATED)
def create_dashboard_constitution(
    request: ConstitutionRequest, session: UserSession
) -> dict[str, Any]:
    return dict(create_constitution(request, _principal(session)))


@router.post("/constitutions/{constitution_id}/confirm")
def confirm_dashboard_constitution(
    constitution_id: UUID,
    request: ConstitutionConfirmationRequest,
    session: UserSession,
) -> dict[str, Any]:
    return dict(confirm_constitution(constitution_id, request, _principal(session)))


@router.post("/experiments/start", status_code=status.HTTP_202_ACCEPTED)
def start_dashboard_experiment(
    request: StartExperimentRequest, response: Response, session: UserSession
) -> dict[str, Any]:
    return dict(start_experiment(request, response, _principal(session)))


@router.get("/experiments/{experiment_id}/evidence")
def dashboard_evidence(experiment_id: UUID, session: UserSession) -> dict[str, Any]:
    return dict(get_experiment_evidence(experiment_id, _principal(session)))


@router.get("/experiments/{experiment_id}/reports/{report_type}")
def dashboard_report(
    experiment_id: UUID, report_type: ReportType, session: UserSession
) -> dict[str, Any]:
    return dict(get_report_reference(experiment_id, report_type, _principal(session)))


@router.get("/experiments/{experiment_id}/reports/{report_type}/content")
def dashboard_report_content(
    experiment_id: UUID, report_type: ReportType, session: UserSession
) -> Response:
    response: Response = get_report_content_response(
        experiment_id, report_type, _principal(session)
    )
    return response


@router.post("/experiments/{experiment_id}/clarifications")
def answer_dashboard_clarification(
    experiment_id: UUID,
    request: ClarificationAnswerRequest,
    session: UserSession,
) -> dict[str, Any]:
    return dict(answer_clarification(experiment_id, request, _principal(session)))


@router.post("/experiments/{experiment_id}/cancel")
def cancel_dashboard_experiment(
    experiment_id: UUID, request: CancelRequest, session: UserSession
) -> dict[str, Any]:
    return dict(cancel_experiment(experiment_id, request, _principal(session)))

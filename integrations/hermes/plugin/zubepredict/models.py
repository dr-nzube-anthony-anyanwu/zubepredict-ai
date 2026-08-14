from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyArguments(ToolArguments):
    pass


class CreateProjectArguments(ToolArguments):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class DatasetArguments(ToolArguments):
    dataset_id: UUID


class UploadDatasetArguments(ToolArguments):
    project_id: UUID
    attachment_path: str = Field(min_length=1, max_length=1000)


class TelegramLinkCodeArguments(ToolArguments):
    code: str = Field(min_length=8, max_length=8, pattern=r"^[0-9]{8}$")


class ReadinessArguments(DatasetArguments):
    objective: str = Field(min_length=3, max_length=2000)


class ConstitutionArguments(ReadinessArguments):
    target: str | None = Field(default=None, max_length=255)


class ConfirmConstitutionArguments(ToolArguments):
    constitution_id: UUID
    constitution_version: int = Field(ge=1)
    confirmed: Literal[True]


class StartExperimentArguments(ToolArguments):
    constitution_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")


class ExperimentArguments(ToolArguments):
    experiment_id: UUID


class ClarificationArguments(ExperimentArguments):
    clarification_id: str = Field(min_length=16, max_length=64, pattern=r"^[0-9a-f]+$")
    clarification_version: int = Field(ge=1)
    response: str = Field(min_length=1, max_length=2000)
    task_type: (
        Literal[
            "binary_classification",
            "multiclass_classification",
            "regression",
            "clustering",
            "anomaly_detection",
            "time_series_forecasting",
        ]
        | None
    ) = None
    target_column: str | None = Field(default=None, max_length=255)
    confirmed_by_user: bool = False


class CancelArguments(ExperimentArguments):
    confirmation: Literal[True]


class ReportArguments(ExperimentArguments):
    report_type: Literal[
        "evidence",
        "evidence_card",
        "html",
        "pdf",
        "model_card",
        "predictions_csv",
        "predictions_xlsx",
        "reproducibility_manifest",
    ]

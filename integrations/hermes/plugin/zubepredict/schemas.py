from __future__ import annotations

from typing import Any


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


UUID = {"type": "string", "format": "uuid"}
DATASET = {"dataset_id": UUID}
EXPERIMENT = {"experiment_id": UUID}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "zubepredict_health": _object({}),
    "zubepredict_list_projects": _object({}),
    "zubepredict_create_project": _object(
        {
            "name": {"type": "string", "minLength": 1, "maxLength": 120},
            "description": {"type": ["string", "null"], "maxLength": 1000},
        },
        ["name"],
    ),
    "zubepredict_upload_dataset": _object(
        {
            "project_id": UUID,
            "attachment_path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1000,
                "description": "Hermes-cached attachment path from the current Telegram message.",
            },
        },
        ["project_id", "attachment_path"],
    ),
    "zubepredict_channel_state": _object({}),
    "zubepredict_reset_channel_state": _object({}),
    "zubepredict_link_telegram_account": _object(
        {"code": {"type": "string", "minLength": 8, "maxLength": 8, "pattern": "^[0-9]{8}$"}},
        ["code"],
    ),
    "zubepredict_profile_dataset": _object(DATASET, ["dataset_id"]),
    "zubepredict_assess_readiness": _object(
        {**DATASET, "objective": {"type": "string", "minLength": 3, "maxLength": 2000}},
        ["dataset_id", "objective"],
    ),
    "zubepredict_create_constitution": _object(
        {
            **DATASET,
            "objective": {"type": "string", "minLength": 3, "maxLength": 2000},
            "target": {"type": ["string", "null"], "maxLength": 255},
        },
        ["dataset_id", "objective"],
    ),
    "zubepredict_confirm_constitution": _object(
        {
            "constitution_id": UUID,
            "constitution_version": {"type": "integer", "minimum": 1},
            "confirmed": {"const": True},
        },
        ["constitution_id", "constitution_version", "confirmed"],
    ),
    "zubepredict_start_experiment": _object(
        {
            "constitution_id": UUID,
            "idempotency_key": {
                "type": "string",
                "minLength": 8,
                "maxLength": 200,
                "pattern": "^[A-Za-z0-9._:-]+$",
            },
        },
        ["constitution_id", "idempotency_key"],
    ),
    "zubepredict_experiment_status": _object(EXPERIMENT, ["experiment_id"]),
    "zubepredict_answer_clarification": _object(
        {
            **EXPERIMENT,
            "clarification_id": {"type": "string", "minLength": 16, "maxLength": 64},
            "clarification_version": {"type": "integer", "minimum": 1},
            "response": {"type": "string", "minLength": 1, "maxLength": 2000},
            "task_type": {
                "type": ["string", "null"],
                "enum": [
                    "binary_classification",
                    "multiclass_classification",
                    "regression",
                    "clustering",
                    "anomaly_detection",
                    "time_series_forecasting",
                    None,
                ],
            },
            "target_column": {"type": ["string", "null"], "maxLength": 255},
            "confirmed_by_user": {"type": "boolean", "default": False},
        },
        ["experiment_id", "clarification_id", "clarification_version", "response"],
    ),
    "zubepredict_cancel_experiment": _object(
        {**EXPERIMENT, "confirmation": {"const": True}},
        ["experiment_id", "confirmation"],
    ),
    "zubepredict_get_evidence": _object(EXPERIMENT, ["experiment_id"]),
    "zubepredict_get_report": _object(
        {
            **EXPERIMENT,
            "report_type": {
                "type": "string",
                "enum": [
                    "evidence",
                    "evidence_card",
                    "html",
                    "pdf",
                    "model_card",
                    "predictions_csv",
                    "predictions_xlsx",
                    "reproducibility_manifest",
                ],
            },
        },
        ["experiment_id", "report_type"],
    ),
}

DESCRIPTIONS = {
    "zubepredict_health": "Check the signed ZubePredict API boundary.",
    "zubepredict_list_projects": "List projects owned by the trusted principal.",
    "zubepredict_create_project": "Create a project for the trusted principal.",
    "zubepredict_upload_dataset": (
        "Transfer one current Telegram attachment through the authorised upload boundary, then "
        "delete the temporary gateway copy. Only CSV, XLSX, and Parquet are accepted."
    ),
    "zubepredict_channel_state": "Read authoritative resumable Telegram workflow state.",
    "zubepredict_reset_channel_state": (
        "Reset Telegram selections without deleting projects, datasets, or experiments."
    ),
    "zubepredict_link_telegram_account": (
        "Redeem a short-lived dashboard linking code using trusted Telegram sender metadata."
    ),
    "zubepredict_profile_dataset": (
        "Return safe metadata for an owned registered dataset; never raw rows."
    ),
    "zubepredict_assess_readiness": (
        "Assess whether an owned dataset can proceed to a constitution."
    ),
    "zubepredict_create_constitution": "Propose a versioned experiment constitution for review.",
    "zubepredict_confirm_constitution": "Explicitly approve an unchanged constitution version.",
    "zubepredict_start_experiment": "Idempotently queue an approved constitution.",
    "zubepredict_experiment_status": (
        "Read durable status and clarification state for an owned experiment."
    ),
    "zubepredict_answer_clarification": (
        "Answer the current versioned clarification and resume processing."
    ),
    "zubepredict_cancel_experiment": "Explicitly request cancellation of an owned experiment.",
    "zubepredict_get_evidence": "Read the immutable evidence envelope for a completed experiment.",
    "zubepredict_get_report": (
        "Read safe report metadata; does not expose storage credentials or raw files."
    ),
}

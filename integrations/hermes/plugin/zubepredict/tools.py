from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

from pydantic import ValidationError

from .api_client import ZubePredictAPIError, ZubePredictClient
from .errors import failure, success
from .models import (
    CancelArguments,
    ClarificationArguments,
    ConfirmConstitutionArguments,
    ConstitutionArguments,
    CreateProjectArguments,
    DatasetArguments,
    EmptyArguments,
    ExperimentArguments,
    ReadinessArguments,
    ReportArguments,
    StartExperimentArguments,
    TelegramLinkCodeArguments,
    ToolArguments,
    UploadDatasetArguments,
)
from .telegram_security import TelegramAccessDenied

T = TypeVar("T", bound=ToolArguments)


def _invoke(model: type[T], args: dict[str, Any], operation: Any) -> str:
    try:
        validated = model.model_validate_json(json.dumps(args))
        return success(operation(validated, ZubePredictClient()))
    except ValidationError:
        return failure("invalid_tool_arguments", "Tool arguments failed strict validation.")
    except KeyError:
        return failure("plugin_not_configured", "Required ZubePredict plugin settings are missing.")
    except ZubePredictAPIError as exc:
        return failure(exc.code, str(exc), retryable=exc.retryable)
    except TelegramAccessDenied:
        return failure("unauthorised", "This Telegram account is not linked or authorised.")
    except Exception:
        return failure("plugin_error", "The ZubePredict tool failed safely.")


def health(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        EmptyArguments, args, lambda _a, c: c.request("GET", "/hermes/health", retry_safe=True)
    )


def list_projects(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        EmptyArguments, args, lambda _a, c: c.request("GET", "/hermes/projects", retry_safe=True)
    )


def create_project(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        CreateProjectArguments,
        args,
        lambda a, c: c.request("POST", "/hermes/projects", payload=a.model_dump(mode="json")),
    )


def _attachment_root() -> Path:
    configured = os.getenv("ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if os.name == "nt" and local_app_data:
        return (Path(local_app_data) / "hermes" / "cache" / "documents").resolve()
    return (Path.home() / ".hermes" / "cache" / "documents").resolve()


def upload_dataset(args: dict[str, Any], **_: Any) -> str:
    def operation(a: UploadDatasetArguments, c: ZubePredictClient) -> Any:
        root = _attachment_root()
        path = Path(a.attachment_path).expanduser().resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(root):
            raise ZubePredictAPIError(
                "invalid_file", "That attachment is not available for upload."
            )
        try:
            media_types = {
                ".csv": "text/csv",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".parquet": "application/vnd.apache.parquet",
            }
            content_type = media_types.get(path.suffix.lower())
            if content_type is None:
                raise ZubePredictAPIError(
                    "invalid_file", "That file type is not supported. Please upload CSV or XLSX."
                )
            try:
                max_bytes = int(os.getenv("ZUBEPREDICT_TELEGRAM_MAX_UPLOAD_MB", "10")) * 1024 * 1024
            except ValueError:
                max_bytes = 10 * 1024 * 1024
            if path.stat().st_size > max_bytes:
                raise ZubePredictAPIError(
                    "file_too_large", "That file is larger than the upload limit."
                )
            content = path.read_bytes()
            return c.upload(
                f"/hermes/projects/{a.project_id}/datasets/upload",
                content=content,
                filename=path.name,
                content_type=content_type,
            )
        finally:
            path.unlink(missing_ok=True)

    return _invoke(UploadDatasetArguments, args, operation)


def channel_state(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        EmptyArguments,
        args,
        lambda _a, c: c.request("GET", "/hermes/channel/state", retry_safe=True),
    )


def reset_channel_state(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        EmptyArguments,
        args,
        lambda _a, c: c.request("POST", "/hermes/channel/state/reset", payload={}),
    )


def link_telegram_account(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        TelegramLinkCodeArguments,
        args,
        lambda a, c: c.request(
            "POST",
            "/hermes/account-links/telegram/redeem",
            payload=a.model_dump(mode="json"),
        ),
    )


def profile_dataset(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        DatasetArguments,
        args,
        lambda a, c: c.request("GET", f"/hermes/datasets/{a.dataset_id}/profile", retry_safe=True),
    )


def assess_readiness(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        ReadinessArguments,
        args,
        lambda a, c: c.request("POST", "/hermes/readiness", payload=a.model_dump(mode="json")),
    )


def create_constitution(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        ConstitutionArguments,
        args,
        lambda a, c: c.request("POST", "/hermes/constitutions", payload=a.model_dump(mode="json")),
    )


def confirm_constitution(args: dict[str, Any], **_: Any) -> str:
    def operation(a: ConfirmConstitutionArguments, c: ZubePredictClient) -> Any:
        payload = a.model_dump(mode="json", exclude={"constitution_id"})
        return c.request(
            "POST", f"/hermes/constitutions/{a.constitution_id}/confirm", payload=payload
        )

    return _invoke(ConfirmConstitutionArguments, args, operation)


def start_experiment(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        StartExperimentArguments,
        args,
        lambda a, c: c.request(
            "POST", "/hermes/experiments/start", payload=a.model_dump(mode="json")
        ),
    )


def experiment_status(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        ExperimentArguments,
        args,
        lambda a, c: c.request(
            "GET", f"/hermes/experiments/{a.experiment_id}/status", retry_safe=True
        ),
    )


def answer_clarification(args: dict[str, Any], **_: Any) -> str:
    def operation(a: ClarificationArguments, c: ZubePredictClient) -> Any:
        payload = a.model_dump(mode="json", exclude={"experiment_id"})
        return c.request(
            "POST", f"/hermes/experiments/{a.experiment_id}/clarifications", payload=payload
        )

    return _invoke(ClarificationArguments, args, operation)


def cancel_experiment(args: dict[str, Any], **_: Any) -> str:
    def operation(a: CancelArguments, c: ZubePredictClient) -> Any:
        return c.request(
            "POST",
            f"/hermes/experiments/{a.experiment_id}/cancel",
            payload={"confirmation": a.confirmation},
        )

    return _invoke(CancelArguments, args, operation)


def get_evidence(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        ExperimentArguments,
        args,
        lambda a, c: c.request(
            "GET", f"/hermes/experiments/{a.experiment_id}/evidence", retry_safe=True
        ),
    )


def get_report(args: dict[str, Any], **_: Any) -> str:
    return _invoke(
        ReportArguments,
        args,
        lambda a, c: c.request(
            "GET",
            f"/hermes/experiments/{a.experiment_id}/reports/{quote(a.report_type, safe='')}",
            retry_safe=True,
        ),
    )

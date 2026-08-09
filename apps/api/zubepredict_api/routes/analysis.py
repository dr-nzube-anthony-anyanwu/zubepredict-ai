from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from zubepredict_core.data_engine.loader import load_dataframe, validate_dimensions
from zubepredict_core.data_engine.profiler import profile_dataframe
from zubepredict_core.data_engine.quality_guardian import assess_data_quality
from zubepredict_core.data_engine.task_detector import detect_task
from zubepredict_core.ml_engine.tournament import run_supervised_tournament
from zubepredict_core.shared.config import get_settings
from zubepredict_core.shared.schemas import (
    DataQualityReport,
    DatasetProfile,
    ExperimentResult,
    TaskDecision,
    TaskType,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])
settings = get_settings()


def _comma_separated(value: str | None) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in (value or "").split(",") if item.strip()))


async def _save_temporary(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "dataset.csv").suffix.lower()
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            total = 0
            while chunk := await upload.read(64 * 1024):
                total += len(chunk)
                if total > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(
                        413, f"File exceeds the {settings.max_upload_mb} MB starter limit."
                    )
                temporary.write(chunk)
        return temporary_path
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


@router.post("/profile", response_model=DatasetProfile)
async def profile(file: UploadFile = File(...)) -> DatasetProfile:
    path = await _save_temporary(file)
    try:
        dataframe = load_dataframe(path)
        validate_dimensions(dataframe, settings.max_rows, settings.max_columns)
        return profile_dataframe(dataframe)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@router.post("/detect-task", response_model=TaskDecision)
async def task_detection(
    file: UploadFile = File(...),
    target_column: str | None = Form(default=None),
    objective: str | None = Form(default=None),
) -> TaskDecision:
    path = await _save_temporary(file)
    try:
        dataframe = load_dataframe(path)
        validate_dimensions(dataframe, settings.max_rows, settings.max_columns)
        return detect_task(dataframe, target_column, objective)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@router.post("/quality", response_model=DataQualityReport)
async def quality_assessment(
    file: UploadFile = File(...),
    target_column: str | None = Form(default=None),
    forbidden_features: str | None = Form(default=None),
    forced_features: str | None = Form(default=None),
    acknowledged_risks: str | None = Form(default=None),
) -> DataQualityReport:
    path = await _save_temporary(file)
    try:
        dataframe = load_dataframe(path)
        validate_dimensions(dataframe, settings.max_rows, settings.max_columns)
        return assess_data_quality(
            dataframe,
            target_column=target_column,
            forbidden_features=_comma_separated(forbidden_features),
            forced_features=_comma_separated(forced_features),
            acknowledged_risks=_comma_separated(acknowledged_risks),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@router.post("/quick-tournament", response_model=ExperimentResult)
async def quick_tournament(
    file: UploadFile = File(...),
    target_column: str = Form(...),
    objective: str | None = Form(default=None),
    forbidden_features: str | None = Form(default=None),
    forced_features: str | None = Form(default=None),
    acknowledged_risks: str | None = Form(default=None),
) -> ExperimentResult:
    path = await _save_temporary(file)
    try:
        dataframe = load_dataframe(path)
        validate_dimensions(dataframe, settings.max_rows, settings.max_columns)
        decision = detect_task(dataframe, target_column, objective)
        if decision.task_type == TaskType.NEEDS_CLARIFICATION:
            raise HTTPException(422, decision.clarification_question or "Clarification required.")
        return run_supervised_tournament(
            dataframe,
            decision,
            seed=settings.random_seed,
            max_models=settings.max_candidate_models,
            compute_budget_seconds=settings.training_timeout_seconds,
            forbidden_features=_comma_separated(forbidden_features),
            forced_features=_comma_separated(forced_features),
            acknowledged_risks=_comma_separated(acknowledged_risks),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)

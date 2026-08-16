from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from zubepredict_core.security import QuotaBackendUnavailable, QuotaExceeded, get_quota_guard
from zubepredict_core.shared.config import get_settings


def enforce_user_rate(owner_id: UUID, action: str = "api.request") -> None:
    settings = get_settings()
    try:
        get_quota_guard().consume(
            owner_id,
            action,
            limit=settings.user_api_requests_per_minute,
            window_seconds=60,
        )
    except QuotaExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "This account is sending requests too quickly. Please wait and try again.",
            headers={"Retry-After": "60"},
        ) from exc
    except QuotaBackendUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Usage limits are temporarily unavailable; the operation was not started.",
        ) from exc


def enforce_experiment_quota(owner_id: UUID, repositories: Any) -> None:
    settings = get_settings()
    experiments = repositories.experiments
    counter = getattr(experiments, "active_count", None)
    active = int(counter()) if callable(counter) else 0
    if active >= settings.user_concurrent_experiments:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "This account already has the maximum number of active experiments.",
            headers={"Retry-After": "30"},
        )
    try:
        get_quota_guard().consume(
            owner_id,
            "experiment.start",
            limit=settings.user_experiments_per_day,
            window_seconds=86_400,
        )
    except QuotaExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "This account has reached its daily experiment limit.",
            headers={"Retry-After": "3600"},
        ) from exc
    except QuotaBackendUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Usage limits are temporarily unavailable; the experiment was not started.",
        ) from exc

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from zubepredict_api.security.user import require_user_session
from zubepredict_core.channels.telegram import TelegramChannelError, TelegramLinkingService
from zubepredict_core.repositories.supabase import (
    AuthenticatedSupabaseSession,
    create_service_repositories,
    create_service_session,
)
from zubepredict_core.shared.config import get_settings

router = APIRouter(prefix="/account-links/telegram", tags=["account-linking"])
UserSession = Annotated[AuthenticatedSupabaseSession, Depends(require_user_session)]


class LinkingCodeRequest(BaseModel):
    ttl_seconds: int | None = Field(default=None, ge=60, le=1800)


def _service(session: AuthenticatedSupabaseSession) -> TelegramLinkingService:
    settings = get_settings()
    try:
        trusted = create_service_session(settings, session.user_id)
        return TelegramLinkingService(
            trusted.client, settings.telegram_linking_code_secret.get_secret_value()
        )
    except TelegramChannelError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def _masked_telegram_id(value: str) -> str:
    suffix = value[-4:] if len(value) >= 4 else value
    return f"••••{suffix}"


@router.get("")
def get_link_status(session: UserSession) -> dict[str, Any]:
    try:
        link = _service(session).get_link(session.user_id)
    except TelegramChannelError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if link is None or link.get("status") != "active":
        return {"linked": False, "status": "not_linked"}
    return {
        "linked": True,
        "status": "active",
        "telegram_user": _masked_telegram_id(str(link.get("external_user_id") or "")),
        "linked_at": link.get("linked_at"),
    }


@router.post("/codes", status_code=status.HTTP_201_CREATED)
def create_linking_code(request: LinkingCodeRequest, session: UserSession) -> dict[str, Any]:
    settings = get_settings()
    ttl = request.ttl_seconds or settings.telegram_linking_code_ttl_seconds
    try:
        code = _service(session).create_code(session.user_id, ttl_seconds=ttl)
        create_service_repositories(settings, session.user_id).audit_logs.record(
            action="telegram.link_code_created",
            resource_type="account_link",
            metadata={"expires_in_seconds": ttl, "source_channel": "web"},
        )
    except TelegramChannelError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {
        "code": code,
        "expires_in_seconds": ttl,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat(),
        "delivery_instruction": "Send /zlink followed by this code in a private bot chat.",
    }


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def revoke_link(session: UserSession) -> Response:
    settings = get_settings()
    try:
        _service(session).revoke(session.user_id)
        create_service_repositories(settings, session.user_id).audit_logs.record(
            action="telegram.link_revoked",
            resource_type="account_link",
            metadata={"source_channel": "web"},
        )
    except TelegramChannelError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request, status
from zubepredict_core.channels.telegram import TelegramChannelError, TelegramLinkingService
from zubepredict_core.repositories.supabase import create_service_session
from zubepredict_core.shared.config import Settings, get_settings

_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIGNATURE_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class TrustedHermesPrincipal:
    """Caller identity established outside LLM-controlled tool arguments."""

    owner_id: UUID
    key_id: str
    channel: str | None = None
    channel_principal: str | None = None


class ReplayCache:
    """Process-local replay protection for the Stage 13 development boundary."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def consume(self, key_id: str, nonce: str, *, now: float, ttl_seconds: int) -> bool:
        key = (key_id, nonce)
        with self._lock:
            expired = [item for item, expiry in self._entries.items() if expiry <= now]
            for item in expired:
                self._entries.pop(item, None)
            if key in self._entries:
                return False
            self._entries[key] = now + ttl_seconds
            return True

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


replay_cache = ReplayCache()


def parse_service_keys(settings: Settings) -> dict[str, str]:
    raw = settings.hermes_service_keys.get_secret_value()
    parsed: dict[str, str] = {}
    for item in raw.split(","):
        if not item.strip() or ":" not in item:
            continue
        key_id, secret = item.split(":", 1)
        key_id = key_id.strip()
        secret = secret.strip()
        if _KEY_ID_PATTERN.fullmatch(key_id) and len(secret) >= 32:
            parsed[key_id] = secret
    return parsed


def canonical_request(
    *,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    principal: str,
    body: bytes,
    channel: str = "",
    channel_principal: str = "",
    content_type: str = "",
    filename: str = "",
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    parts = [method.upper(), path, timestamp, nonce, principal, body_hash]
    if any((channel, channel_principal, content_type, filename)):
        parts.extend([channel, channel_principal, content_type, filename])
    return "\n".join(parts).encode("utf-8")


def sign_request(secret: str, canonical: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


async def _verify_hermes_request(request: Request) -> TrustedHermesPrincipal:
    settings = get_settings()
    key_id = request.headers.get("X-ZubePredict-Key-Id", "")
    timestamp_value = request.headers.get("X-ZubePredict-Timestamp", "")
    nonce = request.headers.get("X-ZubePredict-Nonce", "")
    principal_value = request.headers.get("X-ZubePredict-Principal", "")
    channel = request.headers.get("X-ZubePredict-Channel", "").strip().lower()
    channel_principal = request.headers.get("X-ZubePredict-Channel-Principal", "").strip()
    signed_content_type = request.headers.get("Content-Type", "").strip().lower()
    signed_filename = request.headers.get("X-ZubePredict-Filename", "").strip()
    supplied_signature = request.headers.get("X-ZubePredict-Signature", "").lower()

    if not all((key_id, timestamp_value, nonce, principal_value, supplied_signature)):
        raise _unauthorized("Hermes service authentication is required.")
    if not _KEY_ID_PATTERN.fullmatch(key_id) or not _NONCE_PATTERN.fullmatch(nonce):
        raise _unauthorized("The Hermes service authentication headers are invalid.")
    if not _SIGNATURE_PATTERN.fullmatch(supplied_signature):
        raise _unauthorized("The Hermes service signature is invalid.")

    try:
        timestamp = int(timestamp_value)
        owner_id = UUID(principal_value)
    except (TypeError, ValueError) as exc:
        raise _unauthorized("The Hermes service authentication headers are invalid.") from exc

    now = int(time.time())
    if abs(now - timestamp) > settings.hermes_max_clock_skew_seconds:
        raise _unauthorized("The Hermes service request has expired.")

    keys = parse_service_keys(settings)
    secret = keys.get(key_id)
    if secret is None:
        raise _unauthorized("The Hermes service credential is invalid.")

    canonical = canonical_request(
        method=request.method,
        path=request.url.path,
        timestamp=timestamp_value,
        nonce=nonce,
        principal=principal_value,
        body=await request.body(),
        channel=channel,
        channel_principal=channel_principal,
        content_type=signed_content_type if signed_filename else "",
        filename=signed_filename,
    )
    expected = sign_request(secret, canonical)
    if not hmac.compare_digest(expected, supplied_signature):
        raise _unauthorized("The Hermes service credential is invalid.")

    if channel:
        if channel != "telegram":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "The trusted channel is not allowed.")
        if (
            settings.hermes_telegram_unsafe_allow_all
            or not channel_principal.isascii()
            or not channel_principal.isdigit()
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This Telegram account is not linked or authorised.",
            )
    elif channel_principal:
        raise _unauthorized("The trusted channel headers are invalid.")

    if not replay_cache.consume(
        key_id,
        nonce,
        now=float(now),
        ttl_seconds=settings.hermes_replay_ttl_seconds,
    ):
        raise _unauthorized("The Hermes service request was already used.")
    return TrustedHermesPrincipal(
        owner_id=owner_id,
        key_id=key_id,
        channel=channel or None,
        channel_principal=channel_principal or None,
    )


def _development_owner_allowed(
    settings: Settings, *, claimed_owner: UUID, channel_principal: str
) -> bool:
    configured_owner = settings.hermes_telegram_owner_id.strip()
    return bool(
        settings.app_env.lower() != "production"
        and settings.hermes_dev_principal_id
        and hmac.compare_digest(str(claimed_owner), settings.hermes_dev_principal_id)
        and configured_owner.isascii()
        and configured_owner.isdigit()
        and hmac.compare_digest(channel_principal, configured_owner)
    )


async def require_hermes_linking_principal(request: Request) -> TrustedHermesPrincipal:
    """Authenticate the trusted gateway before an unlinked Telegram user redeems a code."""

    principal = await _verify_hermes_request(request)
    if principal.channel != "telegram" or not principal.channel_principal:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This Telegram account is not linked or authorised."
        )
    settings = get_settings()
    if settings.app_env.lower() != "production" and not _development_owner_allowed(
        settings,
        claimed_owner=principal.owner_id,
        channel_principal=principal.channel_principal,
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This Telegram account is not linked or authorised."
        )
    return principal


async def require_hermes_principal(request: Request) -> TrustedHermesPrincipal:
    principal = await _verify_hermes_request(request)
    settings = get_settings()
    if principal.channel == "telegram" and principal.channel_principal:
        secret = settings.telegram_linking_code_secret.get_secret_value()
        if secret:
            try:
                session = create_service_session(settings, principal.owner_id)
                linked_owner = TelegramLinkingService(session.client, secret).resolve_owner(
                    principal.channel_principal
                )
            except TelegramChannelError as exc:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Telegram account mapping is temporarily unavailable.",
                ) from exc
            if linked_owner is not None:
                return TrustedHermesPrincipal(
                    owner_id=linked_owner,
                    key_id=principal.key_id,
                    channel=principal.channel,
                    channel_principal=principal.channel_principal,
                )
        if _development_owner_allowed(
            settings,
            claimed_owner=principal.owner_id,
            channel_principal=principal.channel_principal,
        ):
            return principal
        if settings.app_env.lower() == "production" and not secret:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Telegram account mapping is not configured.",
            )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This Telegram account is not linked or authorised."
        )

    if settings.app_env.lower() == "production":
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "A production trusted-principal mapper has not been configured.",
        )
    if not settings.hermes_dev_principal_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "HERMES_DEV_PRINCIPAL_ID is required for local Hermes access.",
        )
    if not hmac.compare_digest(str(principal.owner_id), settings.hermes_dev_principal_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The trusted principal is not allowed.")
    return principal

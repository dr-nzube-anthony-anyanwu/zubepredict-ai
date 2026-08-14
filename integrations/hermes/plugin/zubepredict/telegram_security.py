from __future__ import annotations

import hashlib
import hmac
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger("zubepredict.telegram.security")
_TRUE_VALUES = {"1", "true", "yes", "on"}


class TelegramAccessDenied(RuntimeError):
    """Fail-closed denial raised before an LLM-controlled tool reaches FastAPI."""


@dataclass(frozen=True)
class TrustedChannelContext:
    channel: str = ""
    principal: str = ""
    chat_type: str = ""


_EARLY_GATEWAY_CONTEXT: ContextVar[TrustedChannelContext | None] = ContextVar(
    "zubepredict_early_gateway_context", default=None
)


def capture_gateway_context(**kwargs: Any) -> None:
    """Capture transport metadata before Hermes dispatches slash commands.

    Hermes 0.20 dispatches plugin slash commands before binding its normal
    HERMES_SESSION_* ContextVars. The pre-gateway event is still trusted
    transport metadata and includes the fields required for the same fail-closed
    Telegram authorization used by regular tools.
    """

    event = kwargs.get("event")
    source = getattr(event, "source", None)
    platform_value = getattr(source, "platform", "")
    platform = str(getattr(platform_value, "value", platform_value) or "").lower()
    if platform != "telegram":
        _EARLY_GATEWAY_CONTEXT.set(TrustedChannelContext())
        return
    _EARLY_GATEWAY_CONTEXT.set(
        TrustedChannelContext(
            channel="telegram",
            principal=str(getattr(source, "user_id", "") or "").strip(),
            chat_type=str(getattr(source, "chat_type", "") or "").strip().lower(),
        )
    )


def _session_value(name: str) -> str:
    try:
        from gateway.session_context import get_session_env

        return str(get_session_env(name, "") or "").strip()
    except Exception:
        return ""


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _deny(reason: str, sender_id: str = "", chat_type: str = "") -> None:
    # Record only operational metadata. Never record usernames or message content.
    sender_digest = (
        hashlib.sha256(sender_id.encode("utf-8")).hexdigest()[:12] if sender_id else "missing"
    )
    LOGGER.warning(
        "telegram_access_denied reason=%s sender_hash=%s chat_type=%s",
        reason,
        sender_digest,
        chat_type or "missing",
    )
    raise TelegramAccessDenied("This Telegram account is not linked or authorised.")


def validate_startup_configuration() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    owner = os.getenv("ZUBEPREDICT_TELEGRAM_OWNER_ID", "").strip()
    allowed = {
        item.strip() for item in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if item.strip()
    }
    app_env = os.getenv("ZUBEPREDICT_ENV", "development").strip().lower()
    unsafe = any(
        _enabled(name)
        for name in (
            "TELEGRAM_ALLOW_ALL_USERS",
            "GATEWAY_ALLOW_ALL_USERS",
            "ZUBEPREDICT_TELEGRAM_UNSAFE_ALLOW_ALL",
        )
    )
    global_allowed = {
        item.strip() for item in os.getenv("GATEWAY_ALLOWED_USERS", "").split(",") if item.strip()
    }
    if not token:
        raise TelegramAccessDenied("Telegram startup failed: TELEGRAM_BOT_TOKEN is missing.")
    if not owner.isascii() or not owner.isdigit():
        raise TelegramAccessDenied(
            "Telegram startup failed: ZUBEPREDICT_TELEGRAM_OWNER_ID is missing or invalid."
        )
    if unsafe:
        if app_env == "production":
            raise TelegramAccessDenied("Telegram allow-all mode is disabled in production.")
        raise TelegramAccessDenied(
            "Telegram allow-all mode is disabled for the Stage 14 owner-only bot."
        )
    if allowed != {owner} or "*" in allowed:
        raise TelegramAccessDenied(
            "Telegram startup failed: TELEGRAM_ALLOWED_USERS must contain only the owner ID."
        )
    if global_allowed:
        raise TelegramAccessDenied(
            "Telegram startup failed: GATEWAY_ALLOWED_USERS must be empty for owner-only mode."
        )


def trusted_channel_context() -> TrustedChannelContext:
    platform = _session_value("HERMES_SESSION_PLATFORM").lower()
    early_context = _EARLY_GATEWAY_CONTEXT.get()
    if not platform and early_context is not None and early_context.channel == "telegram":
        platform = early_context.channel
        sender_id = early_context.principal
        chat_type = early_context.chat_type
    else:
        sender_id = _session_value("HERMES_SESSION_USER_ID")
        chat_type = _session_value("HERMES_SESSION_CHAT_TYPE").lower()
    if platform != "telegram":
        return TrustedChannelContext()
    try:
        validate_startup_configuration()
    except TelegramAccessDenied:
        _deny("configuration", sender_id, chat_type)
    owner = os.environ["ZUBEPREDICT_TELEGRAM_OWNER_ID"].strip()
    if chat_type not in {"dm", "direct", "private"}:
        _deny("non_private_chat", sender_id, chat_type)
    if not sender_id or not sender_id.isascii() or not sender_id.isdigit():
        _deny("missing_or_invalid_sender", sender_id, chat_type)
    if not hmac.compare_digest(sender_id, owner):
        _deny("sender_not_allowlisted", sender_id, chat_type)
    return TrustedChannelContext(channel="telegram", principal=sender_id, chat_type="dm")

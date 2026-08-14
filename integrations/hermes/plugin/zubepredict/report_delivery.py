from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PendingReportDelivery:
    download_url: str
    download_filename: str
    expires_in_seconds: int
    expires_at_monotonic: float


_LOCK = threading.Lock()
_PENDING_BY_SESSION: dict[str, PendingReportDelivery] = {}
_MAX_PENDING_SESSIONS = 128


def _purge_expired(now: float) -> None:
    expired = [
        session_id
        for session_id, delivery in _PENDING_BY_SESSION.items()
        if delivery.expires_at_monotonic <= now
    ]
    for session_id in expired:
        _PENDING_BY_SESSION.pop(session_id, None)


def _delivery_from_data(data: Any) -> PendingReportDelivery | None:
    try:
        download_url = data.get("download_url") if isinstance(data, dict) else None
        download_filename = data.get("download_filename") if isinstance(data, dict) else None
        expires_in_seconds = data.get("expires_in_seconds") if isinstance(data, dict) else None
        if (
            not isinstance(download_url, str)
            or not download_url.startswith("https://")
            or not isinstance(download_filename, str)
            or not download_filename
            or len(download_filename) > 128
            or any(character in download_filename for character in ("/", "\\", "\r", "\n"))
            or not isinstance(expires_in_seconds, int)
            or expires_in_seconds <= 0
        ):
            return None
    except (AttributeError, TypeError, ValueError):
        return None

    now = time.monotonic()
    return PendingReportDelivery(
        download_url=download_url,
        download_filename=download_filename,
        expires_in_seconds=expires_in_seconds,
        expires_at_monotonic=now + expires_in_seconds,
    )


def remember_report_delivery(session_id: str, tool_result: str) -> None:
    """Keep an authorised report reference until this Hermes turn is finalized."""

    if not session_id:
        return
    try:
        envelope = json.loads(tool_result)
        data: Any = envelope.get("data") if envelope.get("ok") is True else None
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return
    delivery = _delivery_from_data(data)
    if delivery is None:
        return

    now = time.monotonic()
    with _LOCK:
        _purge_expired(now)
        if len(_PENDING_BY_SESSION) >= _MAX_PENDING_SESSIONS:
            oldest_session = min(
                _PENDING_BY_SESSION,
                key=lambda key: _PENDING_BY_SESSION[key].expires_at_monotonic,
            )
            _PENDING_BY_SESSION.pop(oldest_session, None)
        _PENDING_BY_SESSION[session_id] = delivery


def render_report_data(data: Any) -> str | None:
    """Render trusted backend report metadata without an LLM transcription step."""

    delivery = _delivery_from_data(data)
    return _render_delivery(delivery) if delivery is not None else None


def _render_delivery(delivery: PendingReportDelivery) -> str:
    minutes = max(1, (delivery.expires_in_seconds + 59) // 60)
    return (
        f"Your owner-authorized report is ready: {delivery.download_filename}\n\n"
        f"{delivery.download_url}\n\n"
        f"This temporary link expires in about {minutes} minute"
        f"{'s' if minutes != 1 else ''}."
    )


def render_pending_report(response_text: str, session_id: str, platform: str) -> str | None:
    """Return an exact Telegram report reply without asking an LLM to copy its JWT."""

    if not session_id:
        return None
    now = time.monotonic()
    with _LOCK:
        _purge_expired(now)
        delivery = _PENDING_BY_SESSION.pop(session_id, None)
    normalized_platform = platform.strip().casefold().rsplit(".", maxsplit=1)[-1]
    if delivery is None or normalized_platform != "telegram":
        return None

    return _render_delivery(delivery)

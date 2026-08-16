from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from functools import lru_cache
from typing import Any, cast
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from zubepredict_core.shared.config import Settings, get_settings


class QuotaExceeded(RuntimeError):
    """Raised when an owner has exhausted a bounded operation quota."""


class QuotaBackendUnavailable(RuntimeError):
    """Raised when production quota state cannot be checked safely."""


class SecretRedactor:
    """Conservative structured-log redactor; never a substitute for isolation."""

    _SENSITIVE_KEY = re.compile(
        r"(authorization|cookie|token|secret|password|api[_-]?key|service[_-]?role)", re.I
    )
    _BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{12,}")
    _JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")

    @classmethod
    def redact(cls, value: Any, *, key: str = "") -> Any:
        if key and cls._SENSITIVE_KEY.search(key):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(k): cls.redact(v, key=str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls.redact(item) for item in value]
        if isinstance(value, str):
            return cls._JWT.sub("[REDACTED_JWT]", cls._BEARER.sub("Bearer [REDACTED]", value))
        return value


class _RedactingLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = SecretRedactor.redact(str(record.msg))
        if record.args:
            record.args = tuple(SecretRedactor.redact(item) for item in record.args)
        return True


def configure_log_redaction() -> None:
    """Attach one redactor to existing root handlers without printing configuration."""

    root = logging.getLogger()
    if any(isinstance(item, _RedactingLogFilter) for item in root.filters):
        return
    redactor = _RedactingLogFilter()
    root.addFilter(redactor)
    for handler in root.handlers:
        handler.addFilter(redactor)


class QuotaGuard:
    """Distributed fixed-window counters with a development-only memory fallback."""

    _LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return current
"""

    def __init__(self, settings: Settings, redis_client: Redis | None = None) -> None:
        self._settings = settings
        self._redis = redis_client or Redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        self._memory: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(owner_id: UUID, action: str, window_seconds: int, now: int) -> str:
        owner_hash = hashlib.sha256(str(owner_id).encode()).hexdigest()[:24]
        bucket = now // window_seconds
        safe_action = re.sub(r"[^a-z0-9_.-]", "_", action.lower())[:64]
        return f"zubepredict:quota:{safe_action}:{owner_hash}:{bucket}"

    def _memory_consume(self, key: str, window_seconds: int, now: int) -> int:
        with self._lock:
            count, expiry = self._memory.get(key, (0, now + window_seconds))
            if expiry <= now:
                count, expiry = 0, now + window_seconds
            count += 1
            self._memory[key] = (count, expiry)
            return count

    def consume(
        self,
        owner_id: UUID,
        action: str,
        *,
        limit: int,
        window_seconds: int,
        now: int | None = None,
    ) -> int:
        timestamp = int(time.time()) if now is None else now
        key = self._key(owner_id, action, window_seconds, timestamp)
        try:
            result = cast(Any, self._redis).eval(self._LUA, 1, key, str(window_seconds))
            count = int(result)
        except (RedisError, OSError, ValueError) as exc:
            if self._settings.app_env.lower() == "production" and self._settings.quota_fail_closed:
                raise QuotaBackendUnavailable(
                    "Usage limits are temporarily unavailable; the operation was not started."
                ) from exc
            count = self._memory_consume(key, window_seconds, timestamp)
        if count > limit:
            raise QuotaExceeded("This account has reached the current usage limit.")
        return count

    def clear_memory(self) -> None:
        with self._lock:
            self._memory.clear()


def validate_production_security(settings: Settings) -> None:
    """Reject insecure production configuration before the API starts."""

    if settings.app_env.lower() != "production":
        return
    problems: list[str] = []
    if settings.hermes_dev_principal_id:
        problems.append("HERMES_DEV_PRINCIPAL_ID must be empty")
    if settings.hermes_telegram_unsafe_allow_all:
        problems.append("Telegram allow-all must be false")
    if len(settings.telegram_linking_code_secret.get_secret_value()) < 32:
        problems.append("TELEGRAM_LINKING_CODE_SECRET must contain at least 32 characters")
    service_credentials = [
        item.split(":", 1)
        for item in settings.hermes_service_keys.get_secret_value().split(",")
        if ":" in item
    ]
    if not any(
        re.fullmatch(r"[A-Za-z0-9._-]{1,64}", key_id.strip())
        and len(secret.strip()) >= 32
        for key_id, secret in service_credentials
    ):
        problems.append("HERMES_SERVICE_KEYS must contain a rotatable key-id and secret")
    if not settings.supabase_url.startswith("https://"):
        problems.append("SUPABASE_URL must use HTTPS")
    if len(settings.supabase_service_role_key.get_secret_value()) < 20:
        problems.append("SUPABASE_SERVICE_ROLE_KEY is required server-side")
    if not settings.require_dataset_privacy_attestation:
        problems.append("REQUIRE_DATASET_PRIVACY_ATTESTATION must be true")
    if not settings.quota_fail_closed:
        problems.append("QUOTA_FAIL_CLOSED must be true")
    origins = settings.cors_origin_list
    if not origins or any(origin == "*" or origin.startswith("http://") for origin in origins):
        problems.append("CORS_ORIGINS must contain explicit HTTPS origins")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_quota_guard() -> QuotaGuard:
    return QuotaGuard(get_settings())

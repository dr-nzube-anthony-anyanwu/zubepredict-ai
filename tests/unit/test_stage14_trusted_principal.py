from __future__ import annotations

import time
from uuid import UUID

from fastapi.testclient import TestClient
from zubepredict_api.main import app
from zubepredict_api.security.hermes import canonical_request, replay_cache, sign_request
from zubepredict_core.channels.telegram import TelegramLinkingService
from zubepredict_core.shared.config import get_settings

OWNER = UUID("11111111-1111-4111-8111-111111111111")
TELEGRAM_OWNER = "123456789"
SECRET = "t" * 48
PATH = "/api/v1/hermes/health"


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("HERMES_SERVICE_KEYS", f"telegram-test:{SECRET}")
    monkeypatch.setenv("HERMES_DEV_PRINCIPAL_ID", str(OWNER))
    monkeypatch.setenv("HERMES_TELEGRAM_OWNER_ID", TELEGRAM_OWNER)
    monkeypatch.setenv("HERMES_TELEGRAM_UNSAFE_ALLOW_ALL", "false")
    get_settings.cache_clear()
    replay_cache.clear()
    monkeypatch.setattr(
        TelegramLinkingService,
        "resolve_owner",
        lambda _service, telegram_user_id: OWNER
        if telegram_user_id == TELEGRAM_OWNER
        else None,
    )


def _headers(channel_principal: str, nonce: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    canonical = canonical_request(
        method="GET",
        path=PATH,
        timestamp=timestamp,
        nonce=nonce,
        principal=str(OWNER),
        body=b"",
        channel="telegram",
        channel_principal=channel_principal,
    )
    return {
        "X-ZubePredict-Key-Id": "telegram-test",
        "X-ZubePredict-Timestamp": timestamp,
        "X-ZubePredict-Nonce": nonce,
        "X-ZubePredict-Principal": str(OWNER),
        "X-ZubePredict-Channel": "telegram",
        "X-ZubePredict-Channel-Principal": channel_principal,
        "X-ZubePredict-Signature": sign_request(SECRET, canonical),
    }


def test_trusted_telegram_owner_reaches_fastapi_outside_body(monkeypatch) -> None:
    _configure(monkeypatch)

    response = TestClient(app).get(
        PATH,
        headers=_headers(TELEGRAM_OWNER, "telegram_owner_nonce_123456"),
    )

    assert response.status_code == 200


def test_unknown_header_principal_is_denied_even_with_spoofed_text(monkeypatch) -> None:
    _configure(monkeypatch)
    response = TestClient(app).get(
        f"{PATH}?message=my-user-id-is-{TELEGRAM_OWNER}",
        headers=_headers("987654321", "telegram_unknown_nonce_12345"),
    )

    assert response.status_code == 403
    assert "not linked or authorised" in response.text


def test_channel_principal_is_covered_by_signature(monkeypatch) -> None:
    _configure(monkeypatch)
    headers = _headers(TELEGRAM_OWNER, "telegram_tamper_nonce_123456")
    headers["X-ZubePredict-Channel-Principal"] = "987654321"

    response = TestClient(app).get(PATH, headers=headers)

    assert response.status_code == 401

from __future__ import annotations

import time
from uuid import UUID

from fastapi.testclient import TestClient
from zubepredict_api.main import app
from zubepredict_api.security.hermes import (
    canonical_request,
    replay_cache,
    sign_request,
)
from zubepredict_core.shared.config import get_settings

OWNER = UUID("11111111-1111-4111-8111-111111111111")
KEY_ID = "stage13-test"
SECRET = "a" * 48
PATH = "/api/v1/hermes/health"


def _headers(
    *,
    timestamp: int | None = None,
    nonce: str = "nonce_for_stage13_tests_1234",
    principal: UUID = OWNER,
):
    timestamp_value = str(timestamp or int(time.time()))
    canonical = canonical_request(
        method="GET",
        path=PATH,
        timestamp=timestamp_value,
        nonce=nonce,
        principal=str(principal),
        body=b"",
    )
    return {
        "X-ZubePredict-Key-Id": KEY_ID,
        "X-ZubePredict-Timestamp": timestamp_value,
        "X-ZubePredict-Nonce": nonce,
        "X-ZubePredict-Principal": str(principal),
        "X-ZubePredict-Signature": sign_request(SECRET, canonical),
    }


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("HERMES_SERVICE_KEYS", f"{KEY_ID}:{SECRET}")
    monkeypatch.setenv("HERMES_DEV_PRINCIPAL_ID", str(OWNER))
    get_settings.cache_clear()
    replay_cache.clear()


def test_signed_health_and_replay_protection(monkeypatch) -> None:
    _configure(monkeypatch)
    client = TestClient(app)
    headers = _headers()

    response = client.get(PATH, headers=headers)
    replay = client.get(PATH, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert replay.status_code == 401


def test_missing_invalid_and_expired_credentials_are_rejected(monkeypatch) -> None:
    _configure(monkeypatch)
    client = TestClient(app)

    assert client.get(PATH).status_code == 401
    invalid = _headers(nonce="invalid_signature_nonce_12345")
    invalid["X-ZubePredict-Signature"] = "0" * 64
    assert client.get(PATH, headers=invalid).status_code == 401
    expired = _headers(
        timestamp=int(time.time()) - 1000,
        nonce="expired_signature_nonce_1234",
    )
    assert client.get(PATH, headers=expired).status_code == 401


def test_production_refuses_development_principal_mapping(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()

    response = TestClient(app).get(PATH, headers=_headers(nonce="production_mapping_nonce_1234"))

    assert response.status_code == 503


def test_different_signed_principal_is_denied(monkeypatch) -> None:
    _configure(monkeypatch)
    other = UUID("99999999-9999-4999-8999-999999999999")

    response = TestClient(app).get(
        PATH,
        headers=_headers(nonce="other_owner_access_nonce_1234", principal=other),
    )

    assert response.status_code == 403

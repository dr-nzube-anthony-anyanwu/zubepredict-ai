from __future__ import annotations

import hashlib
import hmac

import httpx
import pytest

from integrations.hermes.plugin.zubepredict.api_client import (
    ZubePredictAPIError,
    ZubePredictClient,
)


def _environment(monkeypatch) -> None:
    monkeypatch.setenv("ZUBEPREDICT_API_BASE_URL", "http://testserver/api/v1")
    monkeypatch.setenv("ZUBEPREDICT_HERMES_KEY_ID", "test-key")
    monkeypatch.setenv("ZUBEPREDICT_HERMES_SERVICE_KEY", "s" * 48)
    monkeypatch.setenv("ZUBEPREDICT_HERMES_PRINCIPAL_ID", "11111111-1111-4111-8111-111111111111")


def test_client_signs_the_full_fastapi_path(monkeypatch) -> None:
    _environment(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        timestamp = request.headers["X-ZubePredict-Timestamp"]
        nonce = request.headers["X-ZubePredict-Nonce"]
        principal = request.headers["X-ZubePredict-Principal"]
        body_hash = hashlib.sha256(request.content).hexdigest()
        canonical = "\n".join(
            [request.method, request.url.path, timestamp, nonce, principal, body_hash]
        ).encode()
        expected = hmac.new(b"s" * 48, canonical, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, request.headers["X-ZubePredict-Signature"])
        assert request.url.path == "/api/v1/hermes/health"
        return httpx.Response(200, json={"status": "ok"})

    client = ZubePredictClient(transport=httpx.MockTransport(handler))

    assert client.request("GET", "/hermes/health", retry_safe=True) == {"status": "ok"}


def test_client_returns_stable_backend_unavailable_error(monkeypatch) -> None:
    _environment(monkeypatch)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("sensitive network detail", request=request)

    client = ZubePredictClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ZubePredictAPIError) as captured:
        client.request("GET", "/hermes/health", retry_safe=True)

    assert captured.value.code == "backend_unavailable"
    assert str(captured.value) == "ZubePredict API is unavailable."
    assert attempts == 2

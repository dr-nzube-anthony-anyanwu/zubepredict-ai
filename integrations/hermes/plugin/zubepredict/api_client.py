from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from .auth import ServiceCredential
from .telegram_security import trusted_channel_context


class ZubePredictAPIError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ZubePredictClient:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = os.getenv(
            "ZUBEPREDICT_API_BASE_URL", "http://127.0.0.1:8040/api/v1"
        ).rstrip("/")
        try:
            timeout = min(max(float(os.getenv("ZUBEPREDICT_HERMES_TIMEOUT_SECONDS", "15")), 1), 120)
        except ValueError:
            timeout = 15
        channel_context = trusted_channel_context()
        self.credential = ServiceCredential(
            key_id=os.environ["ZUBEPREDICT_HERMES_KEY_ID"],
            secret=os.environ["ZUBEPREDICT_HERMES_SERVICE_KEY"],
            principal_id=os.environ["ZUBEPREDICT_HERMES_PRINCIPAL_ID"],
            channel=channel_context.channel,
            channel_principal=channel_context.principal,
        )
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        retry_safe: bool = False,
    ) -> Any:
        body = (
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else b""
        )
        request_url = f"{self.base_url}{path}"
        signature_path = urlsplit(request_url).path
        attempts = 2 if retry_safe else 1
        for attempt in range(attempts):
            headers = self.credential.headers(method, signature_path, body)
            headers["Content-Type"] = "application/json"
            try:
                response = self.client.request(method, request_url, content=body, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(0.05)
                    continue
                raise ZubePredictAPIError(
                    "backend_unavailable", "ZubePredict API is unavailable.", retryable=True
                ) from exc
            try:
                data = response.json()
            except ValueError as exc:
                raise ZubePredictAPIError(
                    "invalid_backend_response", "ZubePredict API returned invalid JSON."
                ) from exc
            if response.is_success:
                return data
            detail = data.get("detail", data) if isinstance(data, dict) else {}
            if isinstance(detail, dict):
                code = str(detail.get("code") or f"http_{response.status_code}")
                message = str(detail.get("message") or "ZubePredict request failed.")
            else:
                code, message = f"http_{response.status_code}", "ZubePredict request failed."
            if code == "backend_unavailable":
                message = (
                    "ZubePredict is temporarily unavailable. "
                    "Your existing experiment has not been restarted."
                )
            raise ZubePredictAPIError(code, message, retryable=response.status_code >= 500)
        raise ZubePredictAPIError("backend_unavailable", "ZubePredict API is unavailable.")

    def upload(
        self,
        path: str,
        *,
        content: bytes,
        filename: str,
        content_type: str,
        privacy_attested: bool,
    ) -> Any:
        request_url = f"{self.base_url}{path}"
        signature_path = urlsplit(request_url).path
        headers = self.credential.headers(
            "POST",
            signature_path,
            content,
            content_type=content_type.lower(),
            filename=filename,
            privacy_attested="true" if privacy_attested else "false",
        )
        headers["Content-Type"] = content_type
        try:
            response = self.client.request("POST", request_url, content=content, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ZubePredictAPIError(
                "backend_unavailable", "ZubePredict API is unavailable.", retryable=True
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise ZubePredictAPIError(
                "invalid_backend_response", "ZubePredict API returned invalid JSON."
            ) from exc
        if response.is_success:
            return data
        detail = data.get("detail", data) if isinstance(data, dict) else {}
        if isinstance(detail, dict):
            code = str(detail.get("code") or f"http_{response.status_code}")
            message = str(detail.get("message") or "ZubePredict request failed.")
        else:
            code, message = f"http_{response.status_code}", "ZubePredict request failed."
        if code == "backend_unavailable":
            message = (
                "ZubePredict is temporarily unavailable. "
                "Your existing experiment has not been restarted."
            )
        raise ZubePredictAPIError(code, message, retryable=response.status_code >= 500)

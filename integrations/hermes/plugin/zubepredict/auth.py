from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceCredential:
    key_id: str
    secret: str
    principal_id: str
    channel: str = ""
    channel_principal: str = ""

    def headers(
        self,
        method: str,
        path: str,
        body: bytes,
        *,
        content_type: str = "",
        filename: str = "",
    ) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        body_hash = hashlib.sha256(body).hexdigest()
        parts = [method.upper(), path, timestamp, nonce, self.principal_id, body_hash]
        if any((self.channel, self.channel_principal, content_type, filename)):
            parts.extend([self.channel, self.channel_principal, content_type, filename])
        canonical = "\n".join(parts).encode("utf-8")
        signature = hmac.new(self.secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        headers = {
            "X-ZubePredict-Key-Id": self.key_id,
            "X-ZubePredict-Timestamp": timestamp,
            "X-ZubePredict-Nonce": nonce,
            "X-ZubePredict-Principal": self.principal_id,
            "X-ZubePredict-Signature": signature,
        }
        if self.channel:
            headers["X-ZubePredict-Channel"] = self.channel
            headers["X-ZubePredict-Channel-Principal"] = self.channel_principal
        if filename:
            headers["X-ZubePredict-Filename"] = filename
        return headers

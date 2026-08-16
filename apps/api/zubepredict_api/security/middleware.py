from __future__ import annotations

from uuid import uuid4

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class SecurityBoundaryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, max_request_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_request_bytes = max_request_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid4().hex
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self._max_request_bytes:
                    return Response(
                        "Request is larger than the configured limit.",
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        media_type="text/plain",
                        headers={"X-Request-ID": request_id},
                    )
            except ValueError:
                return Response(
                    "Invalid request size.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    media_type="text/plain",
                    headers={"X-Request-ID": request_id},
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

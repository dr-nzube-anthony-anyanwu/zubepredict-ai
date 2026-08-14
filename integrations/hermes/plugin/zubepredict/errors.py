from __future__ import annotations

import json
from typing import Any


def success(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, default=str, separators=(",", ":"))


def failure(code: str, message: str, *, retryable: bool = False) -> str:
    return json.dumps(
        {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}},
        separators=(",", ":"),
    )

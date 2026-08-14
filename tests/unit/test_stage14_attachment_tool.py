from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from integrations.hermes.plugin.zubepredict import tools
from integrations.hermes.plugin.zubepredict.api_client import ZubePredictAPIError

PROJECT = "22222222-2222-4222-8222-222222222222"


class UploadClient:
    fail = False
    calls: list[dict[str, Any]] = []

    def upload(self, path: str, *, content: bytes, filename: str, content_type: str):
        self.calls.append(
            {
                "path": path,
                "content": content,
                "filename": filename,
                "content_type": content_type,
            }
        )
        if self.fail:
            raise ZubePredictAPIError("backend_unavailable", "Temporary failure.", retryable=True)
        return {"dataset_id": "33333333-3333-4333-8333-333333333333"}


def _configure(monkeypatch, root: Path) -> None:
    UploadClient.calls.clear()
    UploadClient.fail = False
    monkeypatch.setattr(tools, "ZubePredictClient", UploadClient)
    monkeypatch.setenv("ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT", str(root))
    monkeypatch.setenv("ZUBEPREDICT_TELEGRAM_MAX_UPLOAD_MB", "1")


@pytest.mark.skipif(os.name != "nt", reason="Windows managed Hermes cache convention")
def test_default_attachment_root_uses_managed_hermes_cache(monkeypatch, tmp_path) -> None:
    local_app_data = tmp_path / "AppData" / "Local"
    monkeypatch.delenv("ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    assert tools._attachment_root() == (
        local_app_data / "hermes" / "cache" / "documents"
    ).resolve()


def test_valid_cached_csv_transfers_and_cleans_up(monkeypatch, tmp_path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    attachment = root / "safe.csv"
    attachment.write_bytes(b"target,value\n0,10\n")
    _configure(monkeypatch, root)

    result = json.loads(
        tools.upload_dataset({"project_id": PROJECT, "attachment_path": str(attachment)})
    )

    assert result["ok"] is True
    assert UploadClient.calls[0]["path"].endswith(f"/{PROJECT}/datasets/upload")
    assert UploadClient.calls[0]["filename"] == "safe.csv"
    assert not attachment.exists()


def test_interrupted_transfer_still_cleans_gateway_copy(monkeypatch, tmp_path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    attachment = root / "safe.csv"
    attachment.write_bytes(b"target,value\n0,10\n")
    _configure(monkeypatch, root)
    UploadClient.fail = True

    result = json.loads(
        tools.upload_dataset({"project_id": PROJECT, "attachment_path": str(attachment)})
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "backend_unavailable"
    assert not attachment.exists()


def test_malicious_path_and_wrong_extension_are_rejected(monkeypatch, tmp_path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("a,b\n1,2\n", encoding="utf-8")
    unsupported = root / "payload.exe"
    unsupported.write_bytes(b"MZ")
    _configure(monkeypatch, root)

    escaped = json.loads(
        tools.upload_dataset({"project_id": PROJECT, "attachment_path": str(outside)})
    )
    wrong = json.loads(
        tools.upload_dataset({"project_id": PROJECT, "attachment_path": str(unsupported)})
    )

    assert escaped["ok"] is False
    assert wrong["ok"] is False
    assert outside.exists()
    assert not unsupported.exists()
    assert not UploadClient.calls


def test_oversized_attachment_is_rejected_before_transfer(monkeypatch, tmp_path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    attachment = root / "large.csv"
    attachment.write_bytes(b"a" * (1024 * 1024 + 1))
    _configure(monkeypatch, root)

    result = json.loads(
        tools.upload_dataset({"project_id": PROJECT, "attachment_path": str(attachment)})
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "file_too_large"
    assert not attachment.exists()
    assert not UploadClient.calls

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from integrations.hermes.plugin.zubepredict import HANDLERS, tools

PROJECT = "11111111-1111-4111-8111-111111111111"
DATASET = "22222222-2222-4222-8222-222222222222"
EXPERIMENT = "33333333-3333-4333-8333-333333333333"


class MockBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method, path, *, payload=None, retry_safe=False):
        del retry_safe
        self.calls.append((method, path, payload))
        if path == "/hermes/projects":
            return {"project_id": PROJECT, "state": "created"}
        if path.endswith("/profile"):
            return {"dataset_id": DATASET, "rows": 4, "readiness": "profiled"}
        if path == "/hermes/readiness":
            return {"status": "ready_for_constitution", "clarification_questions": []}
        if path == "/hermes/constitutions":
            return {
                "constitution_id": EXPERIMENT,
                "version": 1,
                "approval_status": "proposed",
                "task": "binary_classification",
            }
        if path.endswith("/confirm"):
            return {"constitution_id": EXPERIMENT, "approval_status": "approved"}
        if path == "/hermes/experiments/start":
            return {"experiment_id": EXPERIMENT, "state": "queued", "reused": False}
        if path.endswith("/status"):
            return {"experiment_id": EXPERIMENT, "state": "completed", "progress": 100}
        if "/reports/" in path:
            return {
                "report_id": "44444444-4444-4444-8444-444444444444",
                "access": "short_lived_owner_authorised",
                "expires_in_seconds": 300,
            }
        if path.endswith("/evidence"):
            return {"evidence": {"experiment_id": EXPERIMENT, "verified": True}}
        if path == "/hermes/channel/state":
            return {"state": {"active_experiment_id": EXPERIMENT}}
        if path.endswith("/cancel"):
            return {"experiment_id": EXPERIMENT, "state": "cancelled"}
        return {"status": "ok"}

    def upload(self, path, *, content, filename, content_type, privacy_attested):
        self.calls.append(("UPLOAD", path, {"filename": filename, "content": content_type}))
        assert content.startswith(b"target")
        return {"dataset_id": DATASET, "dataset_fingerprint": "a" * 64, "storage": "private"}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(HANDLERS[name](args))
    assert result["ok"] is True, result
    return result["data"]


def test_mocked_owner_only_conversation_reaches_verified_report(
    monkeypatch, tmp_path: Path
) -> None:
    backend = MockBackend()
    monkeypatch.setattr(tools, "ZubePredictClient", lambda: backend)
    root = tmp_path / "documents"
    root.mkdir()
    attachment = root / "sample.csv"
    attachment.write_bytes(b"target,value\n0,10\n1,20\n")
    monkeypatch.setenv("ZUBEPREDICT_TELEGRAM_ATTACHMENT_ROOT", str(root))

    assert _call("zubepredict_create_project", {"name": "Telegram smoke"})["project_id"] == PROJECT
    assert (
        _call(
            "zubepredict_upload_dataset",
            {
                "project_id": PROJECT,
                "attachment_path": str(attachment),
                "privacy_attested": True,
            },
        )["dataset_id"]
        == DATASET
    )
    assert _call("zubepredict_profile_dataset", {"dataset_id": DATASET})["rows"] == 4
    assert (
        _call(
            "zubepredict_assess_readiness",
            {"dataset_id": DATASET, "objective": "predict target"},
        )["status"]
        == "ready_for_constitution"
    )
    constitution = _call(
        "zubepredict_create_constitution",
        {"dataset_id": DATASET, "objective": "predict target", "target": "target"},
    )
    _call(
        "zubepredict_confirm_constitution",
        {"constitution_id": EXPERIMENT, "constitution_version": 1, "confirmed": True},
    )
    assert (
        _call(
            "zubepredict_start_experiment",
            {"constitution_id": EXPERIMENT, "idempotency_key": "telegram-smoke-001"},
        )["state"]
        == "queued"
    )
    assert (
        _call("zubepredict_experiment_status", {"experiment_id": EXPERIMENT})["state"]
        == "completed"
    )
    assert (
        _call("zubepredict_get_evidence", {"experiment_id": EXPERIMENT})["evidence"]["verified"]
        is True
    )
    assert (
        _call("zubepredict_get_report", {"experiment_id": EXPERIMENT, "report_type": "evidence"})[
            "access"
        ]
        == "short_lived_owner_authorised"
    )
    assert _call("zubepredict_channel_state", {})["state"]["active_experiment_id"] == EXPERIMENT
    assert constitution["approval_status"] == "proposed"
    assert not attachment.exists()
    assert all(
        "owner_id" not in (payload or {})
        for _, _, payload in backend.calls
        if isinstance(payload, dict)
    )


def test_cancellation_requires_literal_confirmation(monkeypatch) -> None:
    backend = MockBackend()
    monkeypatch.setattr(tools, "ZubePredictClient", lambda: backend)

    rejected = json.loads(
        HANDLERS["zubepredict_cancel_experiment"](
            {"experiment_id": EXPERIMENT, "confirmation": False}
        )
    )
    accepted = _call(
        "zubepredict_cancel_experiment",
        {"experiment_id": EXPERIMENT, "confirmation": True},
    )

    assert rejected["ok"] is False
    assert accepted["state"] == "cancelled"

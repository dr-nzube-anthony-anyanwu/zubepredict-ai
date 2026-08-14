from __future__ import annotations

from uuid import UUID

from fastapi import Response
from zubepredict_api.routes import hermes as hermes_routes
from zubepredict_api.routes.hermes import StartExperimentRequest, start_experiment
from zubepredict_api.security.hermes import TrustedHermesPrincipal
from zubepredict_core.repositories.models import ExperimentRecord

OWNER = UUID("11111111-1111-4111-8111-111111111111")
EXPERIMENT = UUID("44444444-4444-4444-8444-444444444444")
PROJECT = UUID("55555555-5555-4555-8555-555555555555")
DATASET = UUID("66666666-6666-4666-8666-666666666666")


class FakeExperiments:
    def __init__(self) -> None:
        self.record = ExperimentRecord(
            id=EXPERIMENT,
            owner_id=OWNER,
            project_id=PROJECT,
            dataset_id=DATASET,
            status="draft",
            configuration={"constitution": {"version": 1, "approval_status": "approved"}},
        )
        self.by_key: dict[str, ExperimentRecord] = {}
        self.queue_count = 0

    def get(self, experiment_id: UUID):
        return self.record if experiment_id == EXPERIMENT else None

    def get_by_idempotency_key(self, key: str):
        return self.by_key.get(key)

    def queue_constitution_job(self, experiment_id: UUID, *, job_id: UUID, idempotency_key: str):
        assert experiment_id == EXPERIMENT
        self.queue_count += 1
        self.record = self.record.model_copy(
            update={"status": "queued", "job_id": job_id, "idempotency_key": idempotency_key}
        )
        self.by_key[idempotency_key] = self.record
        return self.record


class FakeRepositories:
    def __init__(self) -> None:
        self.experiments = FakeExperiments()


def test_start_is_idempotent_and_sends_identifiers_only(monkeypatch) -> None:
    repositories = FakeRepositories()
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(hermes_routes, "_repositories", lambda _principal: repositories)
    monkeypatch.setattr(
        hermes_routes.run_experiment,
        "send",
        lambda experiment_id, owner_id, job_id: sent.append((experiment_id, owner_id, job_id)),
    )
    request = StartExperimentRequest(
        constitution_id=EXPERIMENT, idempotency_key="same-request-0001"
    )
    principal = TrustedHermesPrincipal(owner_id=OWNER, key_id="test")

    first = start_experiment(request, Response(), principal)
    second_response = Response()
    second = start_experiment(request, second_response, principal)

    assert first["reused"] is False
    assert second["reused"] is True
    assert repositories.experiments.queue_count == 1
    assert len(sent) == 1
    assert sent[0][0] == str(EXPERIMENT)
    assert sent[0][1] == str(OWNER)
    assert second_response.status_code == 200

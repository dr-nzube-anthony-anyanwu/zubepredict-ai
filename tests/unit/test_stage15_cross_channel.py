from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from zubepredict_api.main import app
from zubepredict_api.routes import dashboard, hermes
from zubepredict_api.security import hermes as hermes_security
from zubepredict_api.security.hermes import canonical_request, replay_cache, sign_request
from zubepredict_api.security.user import require_user_session
from zubepredict_core.repositories.models import (
    DatasetRecord,
    ExperimentRecord,
    ProjectRecord,
)
from zubepredict_core.shared.config import get_settings

from tests.unit.test_stage14_channel_state import FakeClient

CLAIMED_OWNER = UUID("11111111-1111-4111-8111-111111111111")
LINKED_OWNER = UUID("22222222-2222-4222-8222-222222222222")
TELEGRAM_ID = "123456789"
KEY_ID = "stage15-test"
SERVICE_SECRET = "s" * 48
LINK_SECRET = "l" * 48


def _telegram_headers(path: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = f"stage15_cross_channel_{time.time_ns()}"
    canonical = canonical_request(
        method="GET",
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        principal=str(CLAIMED_OWNER),
        body=b"",
        channel="telegram",
        channel_principal=TELEGRAM_ID,
    )
    return {
        "X-ZubePredict-Key-Id": KEY_ID,
        "X-ZubePredict-Timestamp": timestamp,
        "X-ZubePredict-Nonce": nonce,
        "X-ZubePredict-Principal": str(CLAIMED_OWNER),
        "X-ZubePredict-Channel": "telegram",
        "X-ZubePredict-Channel-Principal": TELEGRAM_ID,
        "X-ZubePredict-Signature": sign_request(SERVICE_SECRET, canonical),
    }


def test_web_project_is_visible_through_linked_telegram_identity(monkeypatch) -> None:
    project = ProjectRecord(
        id=uuid4(), owner_id=LINKED_OWNER, name="Made on web", source_channel="web"
    )
    link_client = FakeClient()
    link_client.tables["telegram_account_links"] = [
        {
            "owner_id": str(LINKED_OWNER),
            "platform": "telegram",
            "external_user_id": TELEGRAM_ID,
            "status": "active",
        }
    ]
    repositories = SimpleNamespace(projects=SimpleNamespace(list=lambda: [project]))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("HERMES_SERVICE_KEYS", f"{KEY_ID}:{SERVICE_SECRET}")
    monkeypatch.setenv("HERMES_DEV_PRINCIPAL_ID", str(CLAIMED_OWNER))
    monkeypatch.setenv("HERMES_TELEGRAM_OWNER_ID", TELEGRAM_ID)
    monkeypatch.setenv("TELEGRAM_LINKING_CODE_SECRET", LINK_SECRET)
    get_settings.cache_clear()
    replay_cache.clear()
    monkeypatch.setattr(
        hermes_security,
        "create_service_session",
        lambda settings, owner_id: SimpleNamespace(client=link_client),
    )

    def repositories_for_owner(settings, owner_id):
        assert owner_id == LINKED_OWNER
        return repositories

    monkeypatch.setattr(hermes, "create_service_repositories", repositories_for_owner)
    path = "/api/v1/hermes/projects"
    response = TestClient(app).get(path, headers=_telegram_headers(path))

    assert response.status_code == 200
    assert response.json()["projects"][0]["untrusted_name"] == "Made on web"
    get_settings.cache_clear()


def test_telegram_experiment_is_visible_in_authenticated_dashboard(monkeypatch) -> None:
    project_id = uuid4()
    dataset_id = uuid4()
    experiment_id = uuid4()
    project = ProjectRecord(
        id=project_id,
        owner_id=LINKED_OWNER,
        name="Shared project",
        source_channel="telegram",
    )
    dataset = DatasetRecord(
        id=dataset_id,
        owner_id=LINKED_OWNER,
        project_id=project_id,
        original_filename="synthetic.csv",
        storage_path="private/path.csv",
        sha256="a" * 64,
        size_bytes=100,
        source_channel="telegram",
    )
    experiment = ExperimentRecord(
        id=experiment_id,
        owner_id=LINKED_OWNER,
        project_id=project_id,
        dataset_id=dataset_id,
        objective="Predict the synthetic target",
        source_channel="telegram",
    )
    repositories = SimpleNamespace(
        projects=SimpleNamespace(list=lambda: [project]),
        datasets=SimpleNamespace(list_for_project=lambda _id: [dataset]),
        experiments=SimpleNamespace(list_for_project=lambda _id: [experiment]),
        model_runs=SimpleNamespace(list_for_experiment=lambda _id: []),
        reports=SimpleNamespace(list_for_experiment=lambda _id: []),
        audit_logs=SimpleNamespace(list_for_resource=lambda **_kwargs: []),
    )
    monkeypatch.setattr(
        dashboard.SupabaseRepositorySet,
        "from_session",
        classmethod(lambda cls, session: repositories),
    )
    app.dependency_overrides[require_user_session] = lambda: SimpleNamespace(
        user_id=LINKED_OWNER
    )
    try:
        response = TestClient(app).get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["experiments"][0]["id"] == str(experiment_id)
    assert response.json()["experiments"][0]["source_channel"] == "telegram"

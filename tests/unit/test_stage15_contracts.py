from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from zubepredict_api.main import app
from zubepredict_api.routes import dashboard
from zubepredict_api.security.user import require_user_session
from zubepredict_core.repositories.models import ProjectRecord

from integrations.hermes.plugin.zubepredict import commands


def test_dashboard_and_linking_routes_require_supabase_auth() -> None:
    client = TestClient(app)

    assert client.get("/api/v1/dashboard/overview").status_code == 401
    assert client.get("/api/v1/account-links/telegram").status_code == 401
    assert client.post("/api/v1/account-links/telegram/codes", json={}).status_code == 401


def test_authenticated_dashboard_project_uses_web_channel_and_session_owner(
    monkeypatch,
) -> None:
    owner = UUID("11111111-1111-4111-8111-111111111111")
    captured: dict[str, object] = {}

    class Projects:
        def create(self, **values):
            captured.update(values)
            return ProjectRecord(id=uuid4(), owner_id=owner, **values)

    repositories = SimpleNamespace(projects=Projects())
    monkeypatch.setattr(
        dashboard.SupabaseRepositorySet,
        "from_session",
        classmethod(lambda cls, session: repositories),
    )
    app.dependency_overrides[require_user_session] = lambda: SimpleNamespace(user_id=owner)
    try:
        response = TestClient(app).post(
            "/api/v1/dashboard/projects",
            json={"name": "Unified project", "description": "Created on the web"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["source_channel"] == "web"
    assert captured["source_channel"] == "web"


def test_link_command_calls_backend_directly_without_llm(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, str]]] = []

    class Backend:
        def request(self, method, path, *, payload=None, **_kwargs):
            calls.append((method, path, payload))
            return {"status": "linked"}

    monkeypatch.setattr(commands, "ZubePredictClient", Backend)

    assert commands.link_command("12345678") == (
        "Telegram is now connected to your ZubePredict account."
    )
    assert calls == [
        ("POST", "/hermes/account-links/telegram/redeem", {"code": "12345678"})
    ]


def test_invalid_link_command_never_calls_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        commands,
        "ZubePredictClient",
        lambda: (_ for _ in ()).throw(AssertionError("backend must not be called")),
    )

    assert "eight-digit" in commands.link_command("my code is 12345678")


def test_stage15_migration_keeps_link_attempts_server_only() -> None:
    sql = Path(
        "infrastructure/supabase/supabase/migrations/"
        "20260814124755_stage15_unified_dashboard_linking.sql"
    ).read_text(encoding="utf-8").lower()

    assert "enable row level security" in sql
    assert "revoke all on public.telegram_linking_attempts from anon, authenticated" in sql
    assert "grant all on public.telegram_linking_attempts to service_role" in sql
    assert "principal_hash" in sql
    assert "raw_code" not in sql
    for channel in ("web", "telegram", "api", "administrative"):
        assert f"'{channel}'" in sql


def test_client_source_contains_no_backend_secret_names() -> None:
    prohibited = (
        "OPENROUTER_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "SUPABASE_SERVICE_ROLE_KEY",
        "HERMES_SERVICE_KEYS",
        "ZUBEPREDICT_HERMES_SERVICE_KEY",
        "DATABASE_URL",
        "REDIS_URL",
    )
    root = Path("apps/web")
    checked = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and "node_modules" not in path.parts
        and ".next" not in path.parts
        and path.name != "package-lock.json"
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in checked)

    assert all(name not in combined for name in prohibited)

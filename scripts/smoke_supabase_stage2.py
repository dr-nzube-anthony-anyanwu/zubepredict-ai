"""Optional real-project Stage 2 RLS smoke test.

The script creates one temporary project for each of two existing test users,
verifies that neither user can read the other's project, and deletes both rows.
It never prints credentials or access tokens.
"""

from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass
from uuid import uuid4

from supabase import create_client
from supabase.client import Client, ClientOptions
from zubepredict_core.repositories.supabase import create_authenticated_repositories
from zubepredict_core.shared.config import Settings


@dataclass(frozen=True)
class TestCredentials:
    email: str
    password: str


def required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def access_token(settings: Settings, credentials: TestCredentials) -> str:
    client = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )
    response = client.auth.sign_in_with_password(
        {"email": credentials.email, "password": credentials.password}
    )
    if not response.session:
        raise RuntimeError("Supabase returned no session for a Stage 2 test user.")
    return response.session.access_token


def temporary_credentials() -> TestCredentials:
    """Return unguessable credentials for a short-lived Supabase test user."""
    return TestCredentials(
        email=f"stage2-smoke-{uuid4().hex}@example.invalid",
        password=secrets.token_urlsafe(32),
    )


def admin_client(settings: Settings) -> Client:
    service_key = settings.supabase_service_role_key.get_secret_value()
    if not service_key:
        raise RuntimeError("Provide both test-user credential pairs or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(
        settings.supabase_url,
        service_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )


def create_temporary_user(client: Client, credentials: TestCredentials) -> str:
    response = client.auth.admin.create_user(
        {
            "email": credentials.email,
            "password": credentials.password,
            "email_confirm": True,
        }
    )
    if not response.user:
        raise RuntimeError("Supabase did not create a temporary Stage 2 test user.")
    return str(response.user.id)


def main() -> int:
    settings = Settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be configured.")

    credential_names = (
        "SUPABASE_TEST_USER_A_EMAIL",
        "SUPABASE_TEST_USER_A_PASSWORD",
        "SUPABASE_TEST_USER_B_EMAIL",
        "SUPABASE_TEST_USER_B_PASSWORD",
    )
    supplied = [bool(os.getenv(name, "").strip()) for name in credential_names]
    if any(supplied) and not all(supplied):
        missing = [
            name for name, present in zip(credential_names, supplied, strict=True) if not present
        ]
        raise RuntimeError(f"Incomplete test-user configuration; missing: {', '.join(missing)}")

    admin: Client | None = None
    temporary_user_ids: list[str] = []
    if all(supplied):
        user_a = TestCredentials(
            required_environment("SUPABASE_TEST_USER_A_EMAIL"),
            required_environment("SUPABASE_TEST_USER_A_PASSWORD"),
        )
        user_b = TestCredentials(
            required_environment("SUPABASE_TEST_USER_B_EMAIL"),
            required_environment("SUPABASE_TEST_USER_B_PASSWORD"),
        )
    else:
        admin = admin_client(settings)
        user_a = temporary_credentials()
        user_b = temporary_credentials()

    project_a = None
    project_b = None
    try:
        if admin:
            temporary_user_ids.append(create_temporary_user(admin, user_a))
            temporary_user_ids.append(create_temporary_user(admin, user_b))

        repositories_a = create_authenticated_repositories(settings, access_token(settings, user_a))
        repositories_b = create_authenticated_repositories(settings, access_token(settings, user_b))
        project_a = repositories_a.projects.create(name="Stage 2 RLS smoke A")
        project_b = repositories_b.projects.create(name="Stage 2 RLS smoke B")
        if repositories_a.projects.get(project_b.id) is not None:
            raise AssertionError("User A could read User B's project.")
        if repositories_b.projects.get(project_a.id) is not None:
            raise AssertionError("User B could read User A's project.")
        print("Stage 2 Supabase RLS smoke test passed for two users.")
        return 0
    finally:
        if project_a is not None:
            repositories_a.projects.delete(project_a.id)
        if project_b is not None:
            repositories_b.projects.delete(project_b.id)
        if admin:
            for user_id in reversed(temporary_user_ids):
                admin.auth.admin.delete_user(user_id)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Stage 2 Supabase smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

"""Live Stage 4 ownership, override, audit, and direct-mutation smoke test.

Creates two temporary Auth users and metadata-only test records. Cleanup removes
all temporary rows and users, and no credential or token is printed.
"""

from __future__ import annotations

import secrets
import sys
from uuid import UUID, uuid4

from supabase import create_client
from supabase.client import Client, ClientOptions
from zubepredict_core.decisions.overrides import TaskOverrideService
from zubepredict_core.repositories.supabase import (
    SupabaseRepositorySet,
    create_authenticated_session,
    create_service_repositories,
)
from zubepredict_core.shared.config import Settings
from zubepredict_core.shared.schemas import TaskType


def client_options() -> ClientOptions:
    return ClientOptions(auto_refresh_token=False, persist_session=False)


def temporary_credentials() -> tuple[str, str]:
    return f"stage4-smoke-{uuid4().hex}@example.invalid", secrets.token_urlsafe(32)


def create_user(admin: Client, email: str, password: str) -> UUID:
    response = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    if not response.user:
        raise RuntimeError("Supabase did not create a Stage 4 temporary user.")
    return UUID(str(response.user.id))


def sign_in(settings: Settings, email: str, password: str) -> str:
    client = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=client_options(),
    )
    response = client.auth.sign_in_with_password({"email": email, "password": password})
    if not response.session:
        raise RuntimeError("Supabase returned no Stage 4 test session.")
    return response.session.access_token


def main() -> int:
    settings = Settings()
    service_key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not settings.supabase_anon_key or not service_key:
        raise RuntimeError("Configure the three SUPABASE_* keys before this live test.")

    admin = create_client(settings.supabase_url, service_key, options=client_options())
    temporary_user_ids: list[UUID] = []
    project_id: UUID | None = None
    experiment_id: UUID | None = None
    repositories_a: SupabaseRepositorySet | None = None
    try:
        email_a, password_a = temporary_credentials()
        email_b, password_b = temporary_credentials()
        owner_a = create_user(admin, email_a, password_a)
        owner_b = create_user(admin, email_b, password_b)
        temporary_user_ids.extend((owner_a, owner_b))
        token_a = sign_in(settings, email_a, password_a)
        token_b = sign_in(settings, email_b, password_b)

        session_a = create_authenticated_session(settings, token_a)
        session_b = create_authenticated_session(settings, token_b)
        repositories_a = SupabaseRepositorySet.from_session(session_a)
        repositories_b = SupabaseRepositorySet.from_session(session_b)
        project = repositories_a.projects.create(name="Stage 4 decision smoke")
        project_id = project.id

        trusted_a = create_service_repositories(settings, owner_a)
        dataset = trusted_a.datasets.register(
            project_id=project.id,
            original_filename="stage4.csv",
            storage_path=f"{owner_a}/{uuid4()}.csv",
            sha256="a" * 64,
            size_bytes=64,
            row_count=30,
            column_count=3,
            profile={"schema_columns": ["age", "price", "churn"]},
            media_type="text/csv",
            file_format="csv",
        )
        experiment = repositories_a.experiments.create(
            project_id=project.id,
            dataset_id=dataset.id,
            objective="Predict customer churn",
            target_column="price",
        )
        experiment_id = experiment.id
        service = TaskOverrideService(settings, session_a, repositories_a)
        updated = service.confirm_override(
            experiment.id,
            task_type=TaskType.BINARY_CLASSIFICATION,
            target_column="churn",
            rationale="The test user explicitly confirmed churn as the labelled outcome.",
            confirmed_by_user=True,
        )
        if updated.decision_version != 2 or updated.decision_source != "user_override":
            raise AssertionError("The confirmed override was not versioned and stored.")
        if len(service.history(experiment.id)) != 2:
            raise AssertionError(
                "The requested and applied override audit events were not visible."
            )
        if repositories_b.experiments.get(experiment.id) is not None:
            raise AssertionError("The second user could read the first user's experiment.")

        direct_update_blocked = False
        try:
            repositories_a.experiments.update_decision(
                experiment.id,
                expected_version=2,
                detected_task=TaskType.REGRESSION.value,
                target_column="price",
                task_confidence=1,
                decision_evidence={},
                decision_source="deterministic",
            )
        except Exception:
            direct_update_blocked = True
        if not direct_update_blocked:
            raise AssertionError("An authenticated client directly mutated protected decisions.")

        print("Stage 4 Supabase override, audit, isolation, and permission smoke test passed.")
        return 0
    finally:
        if experiment_id is not None:
            admin.table("audit_logs").delete().eq("resource_id", str(experiment_id)).execute()
        if project_id is not None and repositories_a is not None:
            repositories_a.projects.delete(project_id)
        for user_id in reversed(temporary_user_ids):
            admin.auth.admin.delete_user(str(user_id))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Stage 4 Supabase smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

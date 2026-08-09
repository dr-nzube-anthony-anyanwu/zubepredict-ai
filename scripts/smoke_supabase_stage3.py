"""Live Stage 3 upload/finalize/isolation/delete smoke test.

Creates two temporary Auth users, one project, and one tiny CSV object. Every
resource is removed in cleanup and no token or credential is printed.
"""

from __future__ import annotations

import secrets
import sys
from uuid import uuid4

from supabase import create_client
from supabase.client import Client, ClientOptions
from zubepredict_core.datasets.lifecycle import DatasetLifecycleService
from zubepredict_core.repositories.supabase import create_authenticated_repositories
from zubepredict_core.shared.config import Settings


def client_options() -> ClientOptions:
    return ClientOptions(auto_refresh_token=False, persist_session=False)


def temporary_credentials() -> tuple[str, str]:
    return f"stage3-smoke-{uuid4().hex}@example.invalid", secrets.token_urlsafe(32)


def create_user(admin: Client, email: str, password: str) -> str:
    response = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    if not response.user:
        raise RuntimeError("Supabase did not create a Stage 3 temporary user.")
    return str(response.user.id)


def sign_in(settings: Settings, email: str, password: str) -> tuple[Client, str]:
    client = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=client_options(),
    )
    response = client.auth.sign_in_with_password({"email": email, "password": password})
    if not response.session:
        raise RuntimeError("Supabase returned no Stage 3 test session.")
    return client, response.session.access_token


def main() -> int:
    settings = Settings()
    service_key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not settings.supabase_anon_key or not service_key:
        raise RuntimeError("Configure the three SUPABASE_* keys before this live test.")

    admin = create_client(settings.supabase_url, service_key, options=client_options())
    temporary_user_ids: list[str] = []
    project_id = None
    dataset_id = None
    audit_resource_id = None
    service_a = None
    repositories_a = None
    try:
        email_a, password_a = temporary_credentials()
        email_b, password_b = temporary_credentials()
        temporary_user_ids.append(create_user(admin, email_a, password_a))
        temporary_user_ids.append(create_user(admin, email_b, password_b))
        client_a, token_a = sign_in(settings, email_a, password_a)
        _, token_b = sign_in(settings, email_b, password_b)

        repositories_a = create_authenticated_repositories(settings, token_a)
        repositories_b = create_authenticated_repositories(settings, token_b)
        project = repositories_a.projects.create(name="Stage 3 lifecycle smoke")
        project_id = project.id
        service_a = DatasetLifecycleService.from_access_token(settings, token_a)
        intent = service_a.prepare_upload(
            project_id=project.id,
            filename="stage3.csv",
            content_type="text/csv",
        )
        csv_bytes = b"target,value\n0,10\n1,20\n"
        client_a.storage.from_(settings.supabase_datasets_bucket).upload_to_signed_url(
            intent.storage_path,
            intent.upload_token,
            csv_bytes,
            {"content-type": "text/csv"},
        )
        finalized = service_a.finalize_upload(
            project_id=project.id,
            storage_path=intent.storage_path,
            filename=intent.original_filename,
            content_type=intent.media_type,
        )
        dataset_id = finalized.dataset.id
        if finalized.dataset.sha256 == "" or finalized.inspection.row_count != 2:
            raise AssertionError("Fingerprint or inspection metadata was not stored.")
        if repositories_b.datasets.get(dataset_id) is not None:
            raise AssertionError("The second user could read the first user's dataset metadata.")

        service_a.delete_dataset(dataset_id)
        audit_resource_id = dataset_id
        dataset_id = None
        if repositories_a.datasets.get(finalized.dataset.id) is not None:
            raise AssertionError("Dataset metadata remained after lifecycle deletion.")
        audit_response = (
            admin.table("audit_logs")
            .select("action")
            .eq("resource_id", str(audit_resource_id))
            .execute()
        )
        if {row["action"] for row in (audit_response.data or [])} != {
            "dataset.deletion_started",
            "dataset.deleted",
        }:
            raise AssertionError("The expected dataset deletion audit events were not stored.")
        admin.table("audit_logs").delete().eq("resource_id", str(audit_resource_id)).execute()
        audit_resource_id = None
        print("Stage 3 Supabase upload, isolation, and audited deletion smoke test passed.")
        return 0
    finally:
        if dataset_id is not None and service_a is not None:
            service_a.delete_dataset(dataset_id)
        if project_id is not None and repositories_a is not None:
            repositories_a.projects.delete(project_id)
        if audit_resource_id is not None:
            admin.table("audit_logs").delete().eq("resource_id", str(audit_resource_id)).execute()
        for user_id in reversed(temporary_user_ids):
            admin.auth.admin.delete_user(user_id)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Stage 3 Supabase smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

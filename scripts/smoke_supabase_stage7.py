"""Live Stage 7 durable job-state and permission smoke test.

Creates one temporary Auth user and metadata-only records. Cleanup cascades the
temporary project and removes the user. No dataset object or secret is printed.
"""

from __future__ import annotations

import hashlib
import secrets
import sys
from uuid import UUID, uuid4

from supabase import create_client
from supabase.client import ClientOptions
from zubepredict_core.repositories.supabase import (
    SupabaseRepositoryError,
    SupabaseRepositorySet,
    create_authenticated_session,
    create_service_repositories,
)
from zubepredict_core.shared.config import Settings


def main() -> int:
    settings = Settings()
    service_key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not settings.supabase_anon_key or not service_key:
        raise RuntimeError("Configure the three SUPABASE_* keys before this live test.")

    options = ClientOptions(auto_refresh_token=False, persist_session=False)
    admin = create_client(settings.supabase_url, service_key, options=options)
    email = f"stage7-smoke-{uuid4().hex}@example.invalid"
    password = secrets.token_urlsafe(32)
    user_id: UUID | None = None
    project_id: UUID | None = None
    authenticated: SupabaseRepositorySet | None = None
    try:
        created = admin.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        if not created.user:
            raise RuntimeError("Supabase did not create the temporary Stage 7 user.")
        user_id = UUID(str(created.user.id))
        login = create_client(settings.supabase_url, settings.supabase_anon_key, options=options)
        signed_in = login.auth.sign_in_with_password({"email": email, "password": password})
        if not signed_in.session:
            raise RuntimeError("Supabase returned no Stage 7 test session.")
        session = create_authenticated_session(settings, signed_in.session.access_token)
        authenticated = SupabaseRepositorySet.from_session(session)
        project = authenticated.projects.create(name="Stage 7 job smoke")
        project_id = project.id

        trusted = create_service_repositories(settings, user_id)
        dataset = trusted.datasets.register(
            project_id=project.id,
            original_filename="stage7.csv",
            storage_path=f"{user_id}/{uuid4()}.csv",
            sha256="7" * 64,
            size_bytes=128,
            row_count=20,
            column_count=2,
            media_type="text/csv",
            file_format="csv",
        )
        key = hashlib.sha256(f"{user_id}:stage7-smoke-key".encode()).hexdigest()
        job_id = uuid4()
        experiment = trusted.experiments.create_job(
            project_id=project.id,
            dataset_id=dataset.id,
            job_id=job_id,
            idempotency_key=key,
            target_column="target",
        )
        existing = trusted.experiments.get_by_idempotency_key(key)
        if existing is None or existing.id != experiment.id:
            raise AssertionError("The idempotency lookup did not return the original job.")

        duplicate_blocked = False
        try:
            trusted.experiments.create_job(
                project_id=project.id,
                dataset_id=dataset.id,
                job_id=uuid4(),
                idempotency_key=key,
            )
        except SupabaseRepositoryError:
            duplicate_blocked = True
        if not duplicate_blocked:
            raise AssertionError("The database accepted a duplicate idempotency key.")

        claimed = trusted.experiments.claim_job(experiment.id, job_id)
        if claimed is None or claimed.status != "profiling" or claimed.attempt_count != 1:
            raise AssertionError("The queued job could not be claimed exactly once.")
        if trusted.experiments.claim_job(experiment.id, job_id) is not None:
            raise AssertionError("A duplicate worker delivery claimed an active job.")
        cancelled = trusted.experiments.request_cancel(experiment.id)
        if cancelled.cancel_requested_at is None:
            raise AssertionError("The running job did not persist its cancellation request.")

        direct_update_blocked = False
        try:
            direct_update = (
                session.client.table("experiments")
                .update({"status": "completed", "progress": 100})
                .eq("id", str(experiment.id))
                .execute()
            )
            direct_update_blocked = not bool(direct_update.data)
        except Exception:
            direct_update_blocked = True
        if not direct_update_blocked:
            raise AssertionError("An authenticated client directly mutated protected job state.")

        print("Stage 7 Supabase job state, idempotency, and permission smoke test passed.")
        return 0
    finally:
        if project_id is not None and authenticated is not None:
            authenticated.projects.delete(project_id)
        if user_id is not None:
            admin.auth.admin.delete_user(str(user_id))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Stage 7 Supabase smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

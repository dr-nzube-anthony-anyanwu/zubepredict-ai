import re
from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2] / "infrastructure" / "supabase" / "001_initial_schema.sql"
).read_text(encoding="utf-8")
NORMALIZED = re.sub(r"\s+", " ", MIGRATION.lower())


def test_all_exposed_tables_enable_rls() -> None:
    for table in (
        "profiles",
        "projects",
        "datasets",
        "experiments",
        "model_runs",
        "reports",
        "audit_logs",
    ):
        assert f"alter table public.{table} enable row level security" in NORMALIZED


def test_policies_are_authenticated_owned_and_optimized() -> None:
    assert "for all to authenticated" in NORMALIZED
    assert "for select to authenticated" in NORMALIZED
    assert "(select auth.uid()) = owner_id" in NORMALIZED
    assert "using (auth.uid() = owner_id)" not in NORMALIZED
    assert "with check ((select auth.uid()) = owner_id)" in NORMALIZED


def test_cross_tenant_relations_use_composite_owner_foreign_keys() -> None:
    for constraint in (
        "datasets_project_owner_fkey",
        "experiments_project_owner_fkey",
        "experiments_dataset_project_owner_fkey",
        "model_runs_experiment_owner_fkey",
        "reports_experiment_owner_fkey",
    ):
        assert f"constraint {constraint}" in NORMALIZED


def test_rls_and_foreign_key_columns_are_indexed() -> None:
    for index in (
        "projects_owner_created_idx",
        "datasets_project_owner_idx",
        "experiments_dataset_project_owner_idx",
        "model_runs_experiment_owner_idx",
        "reports_experiment_owner_idx",
        "audit_logs_owner_created_idx",
    ):
        assert f"create index {index}" in NORMALIZED


def test_data_api_and_service_role_privileges_are_explicit() -> None:
    assert "from anon" in NORMALIZED
    assert "to authenticated" in NORMALIZED
    assert "to service_role" in NORMALIZED
    assert "grant all on table" in NORMALIZED


def test_security_definer_function_is_private_and_revoked() -> None:
    assert "function private.handle_new_user()" in NORMALIZED
    assert "security definer set search_path = ''" in NORMALIZED
    assert "revoke execute on function private.handle_new_user()" in NORMALIZED
    assert "function public.handle_new_user()" not in NORMALIZED


def test_storage_policies_are_user_scoped_and_support_safe_upsert() -> None:
    assert "dataset_objects_owner_update" in NORMALIZED
    assert "on storage.objects for update to authenticated" in NORMALIZED
    assert "(storage.foldername(name))[1] = ((select auth.uid())::text)" in NORMALIZED
    assert "owner_id = ((select auth.uid())::text)" in NORMALIZED

import re
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "infrastructure"
    / "supabase"
    / "supabase"
    / "migrations"
    / "20260809003207_secure_dataset_lifecycle.sql"
)
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8")
NORMALIZED = re.sub(r"\s+", " ", MIGRATION.lower())


def test_stage3_uses_a_numbered_supabase_cli_migration() -> None:
    assert MIGRATION_PATH.name[:14].isdigit()
    assert MIGRATION_PATH.name.endswith("_secure_dataset_lifecycle.sql")


def test_dataset_lifecycle_columns_have_constraints_and_index() -> None:
    for column in (
        "media_type",
        "file_format",
        "retention_status",
        "retention_expires_at",
        "validated_at",
    ):
        assert f"column {column}" in NORMALIZED
    assert "datasets_file_format_check" in NORMALIZED
    assert "datasets_retention_status_check" in NORMALIZED
    assert "datasets_owner_retention_expiry_idx" in NORMALIZED


def test_dataset_metadata_mutations_are_server_only() -> None:
    assert 'drop policy if exists "datasets_own_all"' in NORMALIZED
    assert 'create policy "datasets_own_select"' in NORMALIZED
    assert "revoke insert, update, delete on table public.datasets from authenticated" in NORMALIZED
    assert "grant select on table public.datasets to authenticated" in NORMALIZED


def test_private_bucket_allowlist_matches_supported_uploads() -> None:
    for media_type in (
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.apache.parquet",
    ):
        assert media_type in NORMALIZED

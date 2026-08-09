import re
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "infrastructure"
    / "supabase"
    / "supabase"
    / "migrations"
    / "20260809013027_intent_target_task_decisions.sql"
)
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8")
NORMALIZED = re.sub(r"\s+", " ", MIGRATION.lower())


def test_stage4_uses_a_numbered_supabase_cli_migration() -> None:
    assert MIGRATION_PATH.name[:14].isdigit()
    assert MIGRATION_PATH.name.endswith("_intent_target_task_decisions.sql")


def test_decisions_are_evidenced_versioned_and_constrained() -> None:
    for column in (
        "decision_evidence",
        "decision_source",
        "decision_version",
        "decision_updated_at",
        "task_override_confirmed_at",
    ):
        assert f"column {column}" in NORMALIZED
    assert "experiments_decision_evidence_object_check" in NORMALIZED
    assert "experiments_detected_task_check" in NORMALIZED


def test_authenticated_users_cannot_mutate_decisions_directly() -> None:
    assert 'drop policy if exists "experiments_own_all"' in NORMALIZED
    assert 'create policy "experiments_own_select"' in NORMALIZED
    assert 'create policy "experiments_own_insert"' in NORMALIZED
    assert (
        "revoke insert, update, delete on table public.experiments from authenticated" in NORMALIZED
    )
    assert (
        "grant insert ( project_id, dataset_id, owner_id, objective, target_column, configuration )"
        in NORMALIZED
    )

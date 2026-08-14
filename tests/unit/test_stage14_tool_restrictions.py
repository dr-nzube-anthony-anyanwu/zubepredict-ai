from __future__ import annotations

from pathlib import Path

import yaml

from integrations.hermes.plugin.zubepredict import GUARDRAIL
from integrations.hermes.plugin.zubepredict.schemas import TOOL_SCHEMAS


def test_telegram_example_exposes_only_zubepredict_toolset() -> None:
    config = yaml.safe_load(
        Path("integrations/hermes/config/telegram.example.yaml").read_text(encoding="utf-8")
    )

    assert config["platform_toolsets"]["telegram"] == ["stt", "zubepredict", "no_mcp"]
    assert config["agent"]["disabled_toolsets"] == ["kanban"]
    extra = config["gateway"]["platforms"]["telegram"]["extra"]
    assert extra["allowed_chats"] == ["0"]
    assert extra["group_allow_from"] == []
    assert extra["group_allowed_chats"] == []
    assert extra["guest_mode"] is False
    assert extra["observe_unmentioned_group_messages"] is False
    assert extra["allow_admin_from"] == ["0"]
    assert extra["user_allowed_commands"] == [
        "help",
        "whoami",
        "commands",
        "new",
        "reset",
        "zlink",
        "zreport",
    ]

    env_example = Path("integrations/hermes/config/hermes.env.example").read_text(
        encoding="utf-8"
    )
    assert "AppData\\Local\\hermes\\cache\\documents" in env_example
    assert "YOUR_WINDOWS_USER\\.hermes\\cache\\documents" not in env_example


def test_model_cannot_supply_identity_secrets_or_general_tool_arguments() -> None:
    forbidden = {
        "owner_id",
        "telegram_user_id",
        "service_key",
        "bot_token",
        "shell",
        "command",
        "environment",
        "sql",
        "url",
    }
    all_parameters = {
        parameter for schema in TOOL_SCHEMAS.values() for parameter in schema.get("properties", {})
    }

    assert forbidden.isdisjoint(all_parameters)
    assert "my user ID" in GUARDRAIL
    assert "do not alter or invent evidence" in GUARDRAIL


def test_migration_keeps_channel_tables_server_only() -> None:
    migration = next(
        Path("infrastructure/supabase/supabase/migrations").glob(
            "*_stage14_telegram_channel_state.sql"
        )
    ).read_text(encoding="utf-8")

    for table in (
        "telegram_account_links",
        "telegram_channel_states",
        "telegram_linking_codes",
    ):
        assert f"alter table public.{table} enable row level security" in migration
        assert f"revoke all on public.{table} from anon, authenticated" in migration
    assert "code_hash" in migration
    assert "external_user_id" in migration

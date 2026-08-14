"""Persist and verify the pinned Hermes Telegram least-privilege toolset."""

from __future__ import annotations

import sys

from gateway.slash_access import policy_from_extra
from hermes_cli.config import load_config, save_config
from hermes_cli.tools_config import _get_platform_tools

EXPECTED_RUNTIME_TOOLSETS = {"stt", "zubepredict"}
EXPECTED_USER_COMMANDS = ["help", "whoami", "commands", "new", "reset", "zlink", "zreport"]


def configure() -> None:
    config = load_config()
    config.setdefault("platform_toolsets", {})["telegram"] = [
        "stt",  # Config-only marker makes this list authoritative; STT remains disabled.
        "zubepredict",
        "no_mcp",  # Prevent globally configured MCP servers from entering Telegram.
    ]
    known = config.setdefault("known_builtin_toolsets", {}).setdefault("telegram", [])
    if "bfl" not in known:
        known.append("bfl")

    # Kanban is a non-configurable toolset that the pinned runtime recovers from
    # every platform composite. Its only supported hard suppression is global.
    disabled = config.setdefault("agent", {}).setdefault("disabled_toolsets", [])
    if "kanban" not in disabled:
        disabled.append("kanban")

    telegram = (
        config.setdefault("gateway", {})
        .setdefault("platforms", {})
        .setdefault("telegram", {})
    )
    extra = telegram.setdefault("extra", {})
    extra.update(
        {
            "allowed_chats": ["0"],
            "group_allow_from": [],
            "group_allowed_chats": [],
            "guest_mode": False,
            "observe_unmentioned_group_messages": False,
            "require_mention": True,
            # Hermes disables slash gating when this list is empty. User ID 0
            # is an impossible Telegram principal, so nobody becomes admin.
            "allow_admin_from": ["0"],
            "user_allowed_commands": EXPECTED_USER_COMMANDS.copy(),
        }
    )
    config.setdefault("stt", {})["enabled"] = False
    save_config(config)


def verify() -> None:
    config = load_config()
    resolved = _get_platform_tools(config, "telegram")
    if resolved != EXPECTED_RUNTIME_TOOLSETS:
        unexpected = sorted(resolved - EXPECTED_RUNTIME_TOOLSETS)
        missing = sorted(EXPECTED_RUNTIME_TOOLSETS - resolved)
        raise SystemExit(
            "Telegram tool isolation failed: "
            f"unexpected={unexpected or 'none'} missing={missing or 'none'}"
        )
    if bool(config.get("stt", {}).get("enabled")):
        raise SystemExit("Telegram tool isolation failed: speech-to-text is enabled.")
    try:
        extra = config["gateway"]["platforms"]["telegram"]["extra"]
    except (KeyError, TypeError) as exc:
        raise SystemExit("Telegram command isolation failed: configuration is missing.") from exc
    exact_lists = {
        "allowed_chats": ["0"],
        "group_allow_from": [],
        "group_allowed_chats": [],
        "allow_admin_from": ["0"],
        "user_allowed_commands": EXPECTED_USER_COMMANDS,
    }
    for key, expected in exact_lists.items():
        if type(extra.get(key)) is not list or extra.get(key) != expected:
            raise SystemExit(f"Telegram command isolation failed: {key} is not an exact list.")
    policy = policy_from_extra(extra, "dm")
    if not policy.enabled or not all(
        policy.can_run("safe-owner-check", command) for command in ("zlink", "zreport")
    ):
        raise SystemExit("Telegram command isolation failed: safe product commands are unavailable.")
    if policy.can_run("safe-owner-check", "config"):
        raise SystemExit("Telegram command isolation failed: an admin command is user-accessible.")
    print("Resolved Telegram runtime toolsets: zubepredict only (STT config marker disabled).")
    print("Resolved Telegram slash policy: no admins; seven safe user commands.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"configure", "verify"}:
        raise SystemExit("Usage: configure_telegram_tools.py configure|verify")
    if sys.argv[1] == "configure":
        configure()
    verify()

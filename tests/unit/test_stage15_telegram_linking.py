from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from zubepredict_core.channels.telegram import (
    TelegramChannelError,
    TelegramLinkingService,
)

from tests.unit.test_stage14_channel_state import FakeClient

OWNER_A = UUID("11111111-1111-4111-8111-111111111111")
OWNER_B = UUID("22222222-2222-4222-8222-222222222222")
SECRET = "stage15-linking-secret-that-is-long-enough"


def service(client: FakeClient) -> TelegramLinkingService:
    return TelegramLinkingService(client, SECRET)  # type: ignore[arg-type]


def test_expired_code_is_rejected_without_storing_plaintext() -> None:
    client = FakeClient()
    linking = service(client)
    code = linking.create_code(OWNER_A)
    client.tables["telegram_linking_codes"][0]["expires_at"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()

    with pytest.raises(TelegramChannelError, match="invalid or expired"):
        linking.redeem_code(code, telegram_user_id="10001")

    assert code not in str(client.tables)
    assert client.tables["telegram_linking_attempts"][0]["reason"] == "invalid_or_expired"


def test_wrong_guesses_are_rate_limited_and_never_logged_raw() -> None:
    client = FakeClient()
    linking = service(client)

    for guess in ("00000000", "00000001", "00000002"):
        with pytest.raises(TelegramChannelError, match="invalid or expired"):
            linking.redeem_code(guess, telegram_user_id="10001", max_attempts=3)
        client.tables["telegram_linking_attempts"][-1]["attempted_at"] = datetime.now(
            UTC
        ).isoformat()

    with pytest.raises(TelegramChannelError, match="Too many"):
        linking.redeem_code("00000003", telegram_user_id="10001", max_attempts=3)
    assert "00000003" not in str(client.tables["telegram_linking_attempts"])


def test_one_telegram_identity_cannot_take_over_another_owner() -> None:
    client = FakeClient()
    linking = service(client)
    client.tables["telegram_account_links"] = [
        {
            "id": "existing",
            "owner_id": str(OWNER_A),
            "platform": "telegram",
            "external_user_id": "10001",
            "status": "active",
        }
    ]
    code = linking.create_code(OWNER_B)

    with pytest.raises(TelegramChannelError, match="already linked"):
        linking.redeem_code(code, telegram_user_id="10001")

    assert client.tables["telegram_linking_codes"][-1].get("used_at") is None
    assert client.tables["telegram_linking_attempts"][-1]["reason"] == "identity_conflict"


def test_explicit_development_code_migrates_legacy_owner_without_deleting_experiments() -> None:
    client = FakeClient()
    linking = service(client)
    client.tables["telegram_account_links"] = [
        {
            "id": "legacy-link",
            "owner_id": str(OWNER_A),
            "platform": "telegram",
            "external_user_id": "10001",
            "status": "active",
            "link_source": "development_config",
        }
    ]
    client.tables["telegram_channel_states"] = [
        {"id": "legacy-state", "account_link_id": "legacy-link", "owner_id": str(OWNER_A)}
    ]
    client.tables["experiments"] = [{"id": "preserved-experiment", "owner_id": str(OWNER_A)}]
    code = linking.create_code(OWNER_B)

    assert (
        linking.redeem_code(
            code,
            telegram_user_id="10001",
            allow_development_migration=True,
        )
        == OWNER_B
    )
    assert linking.resolve_owner("10001") == OWNER_B
    assert client.tables["telegram_account_links"][0]["link_source"] == "one_time_code"
    assert client.tables["telegram_channel_states"] == []
    assert client.tables["experiments"] == [
        {"id": "preserved-experiment", "owner_id": str(OWNER_A)}
    ]


def test_legacy_development_link_cannot_migrate_without_explicit_flag() -> None:
    client = FakeClient()
    linking = service(client)
    client.tables["telegram_account_links"] = [
        {
            "id": "legacy-link",
            "owner_id": str(OWNER_A),
            "platform": "telegram",
            "external_user_id": "10001",
            "status": "active",
            "link_source": "development_config",
        }
    ]
    code = linking.create_code(OWNER_B)

    with pytest.raises(TelegramChannelError, match="already linked"):
        linking.redeem_code(code, telegram_user_id="10001")


def test_owner_must_revoke_before_linking_a_different_identity() -> None:
    client = FakeClient()
    linking = service(client)
    client.tables["telegram_account_links"] = [
        {
            "id": "existing",
            "owner_id": str(OWNER_A),
            "platform": "telegram",
            "external_user_id": "10001",
            "status": "active",
        }
    ]
    code = linking.create_code(OWNER_A)

    with pytest.raises(TelegramChannelError, match="Revoke"):
        linking.redeem_code(code, telegram_user_id="20002")


def test_revocation_blocks_resolution_and_allows_explicit_relink() -> None:
    client = FakeClient()
    linking = service(client)
    first = linking.create_code(OWNER_A)
    linking.redeem_code(first, telegram_user_id="10001")
    assert linking.resolve_owner("10001") == OWNER_A

    linking.revoke(OWNER_A)
    assert linking.resolve_owner("10001") is None
    second = linking.create_code(OWNER_A)
    linking.redeem_code(second, telegram_user_id="20002")
    assert linking.resolve_owner("20002") == OWNER_A


def test_new_code_revokes_previous_unused_code() -> None:
    client = FakeClient()
    linking = service(client)
    old_code = linking.create_code(OWNER_A)
    new_code = linking.create_code(OWNER_A)

    with pytest.raises(TelegramChannelError, match="invalid or expired"):
        linking.redeem_code(old_code, telegram_user_id="10001")
    assert linking.redeem_code(new_code, telegram_user_id="10001") == OWNER_A


def test_collision_is_retried_without_overwriting_existing_code(monkeypatch) -> None:
    client = FakeClient()
    linking = service(client)
    collision_hash = linking._hash("00000000")  # noqa: SLF001 - collision contract
    client.tables["telegram_linking_codes"] = [
        {"id": "collision", "owner_id": str(OWNER_B), "code_hash": collision_hash}
    ]
    digits = iter("0000000011111111")
    monkeypatch.setattr(
        "zubepredict_core.channels.telegram.secrets.choice", lambda _: next(digits)
    )

    assert linking.create_code(OWNER_A) == "11111111"

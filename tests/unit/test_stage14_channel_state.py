from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from zubepredict_core.channels.telegram import (
    TelegramChannelError,
    TelegramChannelService,
    TelegramLinkingService,
)
from zubepredict_core.shared.config import Settings


class FakeQuery:
    def __init__(self, client, table: str) -> None:
        self.client = client
        self.table = table
        self.filters: list[tuple[str, str, object]] = []
        self.operation = "select"
        self.payload = None

    def select(self, _columns):
        self.operation = "select"
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def is_(self, column, value):
        self.filters.append(("is", column, value))
        return self

    def gt(self, column, value):
        self.filters.append(("gt", column, value))
        return self

    def limit(self, _value):
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = dict(payload)
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def upsert(self, payload, on_conflict=None):
        del on_conflict
        self.operation = "upsert"
        self.payload = dict(payload)
        return self

    def _matches(self, row):
        for kind, column, value in self.filters:
            current = row.get(column)
            if kind == "eq" and current != value:
                return False
            if kind == "is" and value == "null" and current is not None:
                return False
            if kind == "gt" and not (str(current) > str(value)):
                return False
        return True

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        if self.operation == "select":
            return SimpleNamespace(data=[dict(row) for row in rows if self._matches(row)])
        if self.operation == "insert":
            row = {"id": str(uuid4()), **self.payload}
            rows.append(row)
            return SimpleNamespace(data=[dict(row)])
        if self.operation == "update":
            changed = []
            for row in rows:
                if self._matches(row):
                    row.update(self.payload)
                    changed.append(dict(row))
            return SimpleNamespace(data=changed)
        if self.operation == "delete":
            deleted = [dict(row) for row in rows if self._matches(row)]
            self.client.tables[self.table] = [row for row in rows if not self._matches(row)]
            return SimpleNamespace(data=deleted)
        if self.operation == "upsert":
            existing = next(
                (
                    row
                    for row in rows
                    if row.get("platform") == self.payload.get("platform")
                    and row.get("external_user_id") == self.payload.get("external_user_id")
                ),
                None,
            )
            if existing is None:
                existing = {"id": str(uuid4())}
                rows.append(existing)
            existing.update(self.payload)
            return SimpleNamespace(data=[dict(existing)])
        raise AssertionError(self.operation)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


OWNER = UUID("11111111-1111-4111-8111-111111111111")


def test_authoritative_state_resumes_and_reset_does_not_delete_experiment() -> None:
    client = FakeClient()
    service = TelegramChannelService(client)  # type: ignore[arg-type]
    settings = Settings(_env_file=None, app_env="development")
    experiment_id = str(uuid4())
    client.tables["experiments"] = [{"id": experiment_id, "status": "running"}]

    updated = service.update_state(
        settings,
        owner_id=OWNER,
        telegram_user_id="123456789",
        changes={
            "active_experiment_id": experiment_id,
            "last_safe_interaction_state": "running",
        },
    )
    resumed = TelegramChannelService(client).get_state(  # type: ignore[arg-type]
        settings, owner_id=OWNER, telegram_user_id="123456789"
    )
    reset = service.reset_state(settings, owner_id=OWNER, telegram_user_id="123456789")

    assert resumed["id"] == updated["id"]
    assert resumed["active_experiment_id"] == experiment_id
    assert reset["active_experiment_id"] is None
    assert client.tables["experiments"] == [{"id": experiment_id, "status": "running"}]


def test_separate_users_cannot_share_one_development_link() -> None:
    client = FakeClient()
    service = TelegramChannelService(client)  # type: ignore[arg-type]
    settings = Settings(_env_file=None, app_env="development")
    service.get_state(settings, owner_id=OWNER, telegram_user_id="123456789")

    with pytest.raises(TelegramChannelError, match="not linked"):
        service.get_state(settings, owner_id=uuid4(), telegram_user_id="123456789")


def test_development_mapping_cannot_run_in_production() -> None:
    service = TelegramChannelService(FakeClient())  # type: ignore[arg-type]

    with pytest.raises(TelegramChannelError, match="disabled"):
        service.get_state(
            Settings(_env_file=None, app_env="production"),
            owner_id=OWNER,
            telegram_user_id="123456789",
        )


def test_one_time_linking_code_is_hashed_and_single_use() -> None:
    client = FakeClient()
    service = TelegramLinkingService(client, "l" * 48)  # type: ignore[arg-type]

    code = service.create_code(OWNER)
    stored = client.tables["telegram_linking_codes"][0]
    redeemed = service.redeem_code(code, telegram_user_id="123456789")

    assert redeemed == OWNER
    assert code not in str(stored)
    assert len(stored["code_hash"]) == 64
    with pytest.raises(TelegramChannelError, match="invalid or expired"):
        service.redeem_code(code, telegram_user_id="123456789")

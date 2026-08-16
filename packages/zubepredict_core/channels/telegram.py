from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from supabase import Client

from zubepredict_core.shared.config import Settings


class TelegramChannelError(RuntimeError):
    """Raised at the safe Telegram account-link/state boundary."""


def _now() -> datetime:
    return datetime.now(UTC)


class _ServerTableService:
    def __init__(self, client: Client) -> None:
        self._client = client

    @staticmethod
    def _one(response: Any) -> dict[str, Any] | None:
        data = response.data or []
        return dict(data[0]) if data else None

    @staticmethod
    def _safe_execute(query: Any, action: str) -> Any:
        try:
            return query.execute()
        except Exception as exc:
            raise TelegramChannelError(f"Telegram persistence could not {action}.") from exc


class TelegramChannelService(_ServerTableService):
    """Server-only development link mapper and authoritative workflow state."""

    def ensure_development_link(
        self, settings: Settings, *, owner_id: UUID, telegram_user_id: str
    ) -> dict[str, Any]:
        if settings.app_env.lower() == "production":
            raise TelegramChannelError("Development Telegram account mapping is disabled.")
        if not telegram_user_id.isascii() or not telegram_user_id.isdigit():
            raise TelegramChannelError("The trusted Telegram user ID is invalid.")
        response = self._safe_execute(
            self._client.table("telegram_account_links")
            .select("*")
            .eq("platform", "telegram")
            .eq("external_user_id", telegram_user_id)
            .limit(1),
            "read the account link",
        )
        link = self._one(response)
        if link is not None:
            if link.get("owner_id") != str(owner_id) or link.get("status") != "active":
                raise TelegramChannelError("The Telegram account is not linked or authorised.")
            return link
        inserted = self._safe_execute(
            self._client.table("telegram_account_links").insert(
                {
                    "owner_id": str(owner_id),
                    "platform": "telegram",
                    "external_user_id": telegram_user_id,
                    "status": "active",
                    "link_source": "development_config",
                }
            ),
            "create the development account link",
        )
        link = self._one(inserted)
        if link is None:
            raise TelegramChannelError("Telegram persistence created no account link.")
        return link

    def get_state(
        self, settings: Settings, *, owner_id: UUID, telegram_user_id: str
    ) -> dict[str, Any]:
        link = self.ensure_development_link(
            settings, owner_id=owner_id, telegram_user_id=telegram_user_id
        )
        response = self._safe_execute(
            self._client.table("telegram_channel_states")
            .select("*")
            .eq("account_link_id", str(link["id"]))
            .eq("owner_id", str(owner_id))
            .limit(1),
            "read channel state",
        )
        state = self._one(response)
        if state is not None:
            updated_at = state.get("updated_at")
            try:
                last_active = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                last_active = datetime.min.replace(tzinfo=UTC)
            if last_active <= _now() - timedelta(seconds=settings.telegram_session_ttl_seconds):
                expired = self._safe_execute(
                    self._client.table("telegram_channel_states")
                    .update(
                        {
                            "selected_project_id": None,
                            "selected_dataset_id": None,
                            "active_experiment_id": None,
                            "pending_clarification_id": None,
                            "pending_clarification_version": None,
                            "constitution_id": None,
                            "constitution_version": None,
                            "approval_status": "none",
                            "last_safe_interaction_state": "reset",
                            "updated_at": _now().isoformat(),
                        }
                    )
                    .eq("id", str(state["id"]))
                    .eq("owner_id", str(owner_id)),
                    "expire channel state",
                )
                refreshed = self._one(expired)
                if refreshed is None:
                    raise TelegramChannelError("Telegram persistence expired no channel state.")
                return refreshed
            return state
        inserted = self._safe_execute(
            self._client.table("telegram_channel_states").insert(
                {"owner_id": str(owner_id), "account_link_id": str(link["id"])}
            ),
            "create channel state",
        )
        state = self._one(inserted)
        if state is None:
            raise TelegramChannelError("Telegram persistence created no channel state.")
        return state

    def update_state(
        self,
        settings: Settings,
        *,
        owner_id: UUID,
        telegram_user_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        state = self.get_state(settings, owner_id=owner_id, telegram_user_id=telegram_user_id)
        allowed = {
            "selected_project_id",
            "selected_dataset_id",
            "active_experiment_id",
            "pending_clarification_id",
            "pending_clarification_version",
            "constitution_id",
            "constitution_version",
            "approval_status",
            "last_safe_interaction_state",
        }
        payload = {key: value for key, value in changes.items() if key in allowed}
        if not payload:
            return state
        payload["updated_at"] = _now().isoformat()
        response = self._safe_execute(
            self._client.table("telegram_channel_states")
            .update(payload)
            .eq("id", str(state["id"]))
            .eq("owner_id", str(owner_id)),
            "update channel state",
        )
        updated = self._one(response)
        if updated is None:
            raise TelegramChannelError("Telegram persistence updated no channel state.")
        return updated

    def reset_state(
        self, settings: Settings, *, owner_id: UUID, telegram_user_id: str
    ) -> dict[str, Any]:
        return self.update_state(
            settings,
            owner_id=owner_id,
            telegram_user_id=telegram_user_id,
            changes={
                "selected_project_id": None,
                "selected_dataset_id": None,
                "active_experiment_id": None,
                "pending_clarification_id": None,
                "pending_clarification_version": None,
                "constitution_id": None,
                "constitution_version": None,
                "approval_status": "none",
                "last_safe_interaction_state": "reset",
            },
        )


class TelegramLinkingService(_ServerTableService):
    """Stage 15-ready one-time link contract; plaintext codes are never stored."""

    def __init__(self, client: Client, secret: str) -> None:
        super().__init__(client)
        if len(secret) < 32:
            raise TelegramChannelError("Telegram linking-code secret is not configured.")
        self._secret = secret.encode("utf-8")

    def _hash(self, code: str) -> str:
        return hmac.new(self._secret, code.encode("ascii"), hashlib.sha256).hexdigest()

    def _principal_hash(self, telegram_user_id: str) -> str:
        return hmac.new(
            self._secret, f"telegram:{telegram_user_id}".encode(), hashlib.sha256
        ).hexdigest()

    def _record_attempt(self, telegram_user_id: str, *, succeeded: bool, reason: str) -> None:
        self._safe_execute(
            self._client.table("telegram_linking_attempts").insert(
                {
                    "principal_hash": self._principal_hash(telegram_user_id),
                    "succeeded": succeeded,
                    "reason": reason,
                }
            ),
            "record a linking attempt",
        )

    def _enforce_rate_limit(
        self, telegram_user_id: str, *, max_attempts: int, window_seconds: int
    ) -> None:
        cutoff = (_now() - timedelta(seconds=window_seconds)).isoformat()
        response = self._safe_execute(
            self._client.table("telegram_linking_attempts")
            .select("id")
            .eq("principal_hash", self._principal_hash(telegram_user_id))
            .eq("succeeded", False)
            .gt("attempted_at", cutoff),
            "check the linking attempt limit",
        )
        if len(response.data or []) >= max_attempts:
            raise TelegramChannelError("Too many linking attempts. Please wait and try again.")

    def create_code(self, owner_id: UUID, *, ttl_seconds: int = 600) -> str:
        if not 60 <= ttl_seconds <= 1800:
            raise TelegramChannelError("Linking-code lifetime is outside the safe range.")
        now = _now().isoformat()
        self._safe_execute(
            self._client.table("telegram_linking_codes")
            .update({"revoked_at": now})
            .eq("owner_id", str(owner_id))
            .is_("used_at", "null")
            .is_("revoked_at", "null"),
            "revoke older linking codes",
        )
        code = ""
        for _ in range(5):
            candidate = "".join(secrets.choice("0123456789") for _ in range(8))
            existing = self._safe_execute(
                self._client.table("telegram_linking_codes")
                .select("id")
                .eq("code_hash", self._hash(candidate))
                .limit(1),
                "check a linking-code collision",
            )
            if not (existing.data or []):
                code = candidate
                break
        if not code:
            raise TelegramChannelError("A unique linking code could not be generated.")
        expires = _now() + timedelta(seconds=ttl_seconds)
        self._safe_execute(
            self._client.table("telegram_linking_codes").insert(
                {
                    "owner_id": str(owner_id),
                    "code_hash": self._hash(code),
                    "expires_at": expires.isoformat(),
                }
            ),
            "create a one-time linking code",
        )
        return code

    def get_link(self, owner_id: UUID) -> dict[str, Any] | None:
        response = self._safe_execute(
            self._client.table("telegram_account_links")
            .select("*")
            .eq("owner_id", str(owner_id))
            .eq("platform", "telegram")
            .limit(1),
            "read the Telegram account link",
        )
        return self._one(response)

    def resolve_owner(self, telegram_user_id: str) -> UUID | None:
        if not telegram_user_id.isascii() or not telegram_user_id.isdigit():
            return None
        response = self._safe_execute(
            self._client.table("telegram_account_links")
            .select("owner_id")
            .eq("platform", "telegram")
            .eq("external_user_id", telegram_user_id)
            .eq("status", "active")
            .limit(1),
            "resolve the Telegram account link",
        )
        record = self._one(response)
        return UUID(str(record["owner_id"])) if record else None

    def redeem_code(
        self,
        code: str,
        *,
        telegram_user_id: str,
        max_attempts: int = 5,
        window_seconds: int = 600,
        allow_development_migration: bool = False,
    ) -> UUID:
        if not telegram_user_id.isascii() or not telegram_user_id.isdigit():
            raise TelegramChannelError("The linking code is invalid or expired.")
        self._enforce_rate_limit(
            telegram_user_id, max_attempts=max_attempts, window_seconds=window_seconds
        )
        if len(code) != 8 or not code.isascii() or not code.isdigit():
            self._record_attempt(telegram_user_id, succeeded=False, reason="invalid")
            raise TelegramChannelError("The linking code is invalid or expired.")
        response = self._safe_execute(
            self._client.table("telegram_linking_codes")
            .select("*")
            .eq("code_hash", self._hash(code))
            .is_("used_at", "null")
            .is_("revoked_at", "null")
            .gt("expires_at", _now().isoformat())
            .limit(1),
            "verify a one-time linking code",
        )
        record = self._one(response)
        if record is None:
            self._record_attempt(telegram_user_id, succeeded=False, reason="invalid_or_expired")
            raise TelegramChannelError("The linking code is invalid or expired.")
        owner_id = UUID(str(record["owner_id"]))
        external_link_response = self._safe_execute(
            self._client.table("telegram_account_links")
            .select("*")
            .eq("platform", "telegram")
            .eq("external_user_id", telegram_user_id)
            .limit(1),
            "check the Telegram identity owner",
        )
        external_link = self._one(external_link_response)
        legacy_development_link = bool(
            allow_development_migration
            and external_link is not None
            and external_link.get("status") == "active"
            and external_link.get("link_source") == "development_config"
            and external_link.get("owner_id") != str(owner_id)
        )
        if (
            external_link is not None
            and external_link.get("status") == "active"
            and external_link.get("owner_id") != str(owner_id)
            and not legacy_development_link
        ):
            self._record_attempt(telegram_user_id, succeeded=False, reason="identity_conflict")
            raise TelegramChannelError("This Telegram account is already linked.")
        owner_link = self.get_link(owner_id)
        if (
            owner_link is not None
            and owner_link.get("status") == "active"
            and owner_link.get("external_user_id") != telegram_user_id
        ):
            self._record_attempt(telegram_user_id, succeeded=False, reason="owner_conflict")
            raise TelegramChannelError("Revoke the existing Telegram link before re-linking.")
        used_at = _now().isoformat()
        claimed = self._safe_execute(
            self._client.table("telegram_linking_codes")
            .update({"used_at": used_at})
            .eq("id", str(record["id"]))
            .is_("used_at", "null"),
            "consume a one-time linking code",
        )
        if self._one(claimed) is None:
            raise TelegramChannelError("The linking code was already used.")
        payload = {
            "owner_id": str(owner_id),
            "platform": "telegram",
            "external_user_id": telegram_user_id,
            "status": "active",
            "link_source": "one_time_code",
            "linked_at": used_at,
            "updated_at": used_at,
            "revoked_at": None,
        }
        linked: Any
        if legacy_development_link and external_link is not None:
            self._safe_execute(
                self._client.table("telegram_channel_states")
                .delete()
                .eq("account_link_id", str(external_link["id"])),
                "clear the obsolete development channel state",
            )
            linked = self._client.table("telegram_account_links").update(payload).eq(
                "id", str(external_link["id"])
            )
        elif owner_link is not None:
            linked = self._client.table("telegram_account_links").update(payload).eq(
                "id", str(owner_link["id"])
            )
        else:
            linked = self._client.table("telegram_account_links").insert(payload)
        self._safe_execute(linked, "link the Telegram account")
        self._record_attempt(telegram_user_id, succeeded=True, reason="linked")
        return owner_id

    def revoke(self, owner_id: UUID) -> None:
        now = _now().isoformat()
        self._safe_execute(
            self._client.table("telegram_linking_codes")
            .update({"revoked_at": now})
            .eq("owner_id", str(owner_id))
            .is_("used_at", "null")
            .is_("revoked_at", "null"),
            "revoke outstanding linking codes",
        )
        self._safe_execute(
            self._client.table("telegram_account_links")
            .update({"status": "revoked", "revoked_at": now, "updated_at": now})
            .eq("owner_id", str(owner_id))
            .eq("platform", "telegram"),
            "revoke the Telegram account link",
        )

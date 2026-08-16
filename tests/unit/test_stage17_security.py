from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from zubepredict_core.datasets.lifecycle import DatasetLifecycleError, _require_privacy_attestation
from zubepredict_core.security import (
    QuotaBackendUnavailable,
    QuotaExceeded,
    QuotaGuard,
    SecretRedactor,
    validate_production_security,
)
from zubepredict_core.shared.config import Settings

from integrations.hermes.plugin.zubepredict.models import UploadDatasetArguments

ROOT = Path(__file__).resolve().parents[2]
OWNER = UUID("11111111-1111-4111-8111-111111111111")


class FakeRedis:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.values: dict[str, int] = {}

    def eval(self, _script: str, _keys: int, key: str, _window: int) -> int:
        if self.unavailable:
            raise RedisConnectionError("not available")
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


def test_distributed_quota_denies_after_limit_without_raw_owner_in_key() -> None:
    backend = FakeRedis()
    guard = QuotaGuard(Settings(_env_file=None, app_env="production"), backend)  # type: ignore[arg-type]
    assert guard.consume(OWNER, "experiment.start", limit=2, window_seconds=60, now=60) == 1
    assert guard.consume(OWNER, "experiment.start", limit=2, window_seconds=60, now=60) == 2
    with pytest.raises(QuotaExceeded):
        guard.consume(OWNER, "experiment.start", limit=2, window_seconds=60, now=60)
    assert all(str(OWNER) not in key for key in backend.values)


def test_quota_state_failure_is_closed_in_production_and_local_only_falls_back() -> None:
    unavailable = FakeRedis(unavailable=True)
    production = QuotaGuard(
        Settings(_env_file=None, app_env="production"), unavailable  # type: ignore[arg-type]
    )
    with pytest.raises(QuotaBackendUnavailable):
        production.consume(OWNER, "dataset.upload", limit=2, window_seconds=60, now=60)
    development = QuotaGuard(
        Settings(_env_file=None, app_env="development"), unavailable  # type: ignore[arg-type]
    )
    assert development.consume(OWNER, "dataset.upload", limit=2, window_seconds=60, now=60) == 1


def test_secret_redactor_handles_structured_values_bearers_and_jwts() -> None:
    jwt_like = "eyJ" + "abcdefgh.abcdefgh.abcdefgh"
    redacted = SecretRedactor.redact(
        {
            "telegram_bot_token": "example-secret-that-must-not-log",
            "message": f"Bearer abcdefghijklmnopqrstuvwxyz {jwt_like}",
            "safe": "queued",
        }
    )
    assert redacted["telegram_bot_token"] == "[REDACTED]"
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted["message"]
    assert jwt_like not in redacted["message"]
    assert redacted["safe"] == "queued"


def test_production_configuration_rejects_development_or_fail_open_controls() -> None:
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        validate_production_security(Settings(_env_file=None, app_env="production"))
    validate_production_security(
        Settings(
            _env_file=None,
            app_env="production",
            cors_origins="https://app.example.test",
            hermes_service_keys="prod-key:" + "s" * 48,
            telegram_linking_code_secret="l" * 48,
            supabase_url="https://project.supabase.co",
            supabase_service_role_key="service-role-credential-value",
            require_dataset_privacy_attestation=True,
            quota_fail_closed=True,
        )
    )


def test_privacy_attestation_is_mandatory_only_when_configured() -> None:
    _require_privacy_attestation(Settings(), False)
    with pytest.raises(DatasetLifecycleError, match="direct identifiers"):
        _require_privacy_attestation(
            Settings(require_dataset_privacy_attestation=True), False
        )
    _require_privacy_attestation(Settings(require_dataset_privacy_attestation=True), True)


def test_telegram_upload_requires_explicit_true_attestation_and_forbids_extra_fields() -> None:
    valid = UploadDatasetArguments.model_validate(
        {"project_id": OWNER, "attachment_path": "safe.csv", "privacy_attested": True}
    )
    assert valid.privacy_attested is True
    with pytest.raises(ValidationError):
        UploadDatasetArguments.model_validate(
            {"project_id": OWNER, "attachment_path": "safe.csv", "privacy_attested": False}
        )
    with pytest.raises(ValidationError):
        UploadDatasetArguments.model_validate(
            {
                "project_id": OWNER,
                "attachment_path": "safe.csv",
                "privacy_attested": True,
                "owner_id": str(OWNER),
            }
        )


def test_stage17_migration_and_runtime_files_preserve_fail_closed_boundaries() -> None:
    migration = (
        ROOT
        / "infrastructure/supabase/supabase/migrations"
        / "20260815002438_stage17_security_quotas_retention.sql"
    ).read_text(encoding="utf-8").lower()
    assert "revoke insert, update, delete on table public.audit_logs" in migration
    assert "reports_retention_status_check" in migration
    assert "experiments_owner_active_quota_idx" in migration
    assert "private.enforce_owner_resource_limits" in migration
    assert "pg_advisory_xact_lock" in migration
    assert "revoke all on table public.user_security_limits" in migration
    startup = (ROOT / "integrations/hermes/start-telegram-gateway.ps1").read_text(
        encoding="utf-8"
    )
    assert "3c27eb6234bf91b8ceee9e9071591b31e9b148cb" in startup
    assert "revision does not match the reviewed pin" in startup
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "conversation*.db" in ignored
    manifest = (ROOT / "integrations/hermes/plugin/zubepredict/plugin.yaml").read_text(
        encoding="utf-8"
    )
    for prohibited in ("terminal", "shell", "filesystem", "cron", "install_package"):
        assert f"  - {prohibited}" not in manifest

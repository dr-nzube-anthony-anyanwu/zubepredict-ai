from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "ZubePredict AI"
    api_base_url: str = "http://localhost:8040"
    cors_origins: str = "http://localhost:3040"
    redis_url: str = "redis://localhost:6379/0"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_datasets_bucket: str = "datasets"
    supabase_artifacts_bucket: str = "artifacts"

    llm_provider: Literal["template", "openrouter", "ollama"] = "template"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M"
    llm_timeout_seconds: int = 60

    hermes_service_keys: SecretStr = SecretStr("")
    hermes_dev_principal_id: str = ""
    hermes_request_timeout_seconds: int = Field(default=15, ge=1, le=120)
    hermes_max_clock_skew_seconds: int = Field(default=300, ge=30, le=3600)
    hermes_replay_ttl_seconds: int = Field(default=600, ge=60, le=7200)
    hermes_telegram_owner_id: str = ""
    hermes_telegram_unsafe_allow_all: bool = False
    hermes_telegram_report_ttl_seconds: int = Field(default=300, ge=60, le=900)
    telegram_linking_code_secret: SecretStr = SecretStr("")
    telegram_linking_code_ttl_seconds: int = Field(default=600, ge=60, le=1800)
    telegram_linking_max_attempts: int = Field(default=5, ge=3, le=20)
    telegram_linking_attempt_window_seconds: int = Field(default=600, ge=60, le=3600)

    # Disabled aiogram fallback only. The Stage 14 primary token belongs in
    # the Hermes secret environment as TELEGRAM_BOT_TOKEN.
    telegram_bot_token: str = ""
    telegram_mode: Literal["polling", "webhook"] = "polling"

    max_upload_mb: int = Field(default=10, ge=1, le=500)
    max_rows: int = Field(default=50_000, ge=100, le=5_000_000)
    max_columns: int = Field(default=100, ge=2, le=10_000)
    dataset_preview_rows: int = Field(default=25, ge=1, le=200)
    dataset_preview_columns: int = Field(default=25, ge=1, le=100)
    dataset_retention_days: int = Field(default=30, ge=1, le=3650)
    training_timeout_seconds: int = Field(default=600, ge=10, le=86_400)
    max_candidate_models: int = Field(default=5, ge=1, le=20)
    max_optuna_trials: int = Field(default=10, ge=1, le=1_000)
    optuna_timeout_seconds: int = Field(default=120, ge=5, le=86_400)
    user_max_optuna_trials: int = Field(default=20, ge=1, le=10_000)
    user_optuna_timeout_seconds: int = Field(default=180, ge=5, le=86_400)
    tuning_max_candidates: int = Field(default=2, ge=1, le=10)
    explanation_max_sample_rows: int = Field(default=200, ge=10, le=5_000)
    explanation_background_rows: int = Field(default=50, ge=5, le=1_000)
    explanation_local_rows: int = Field(default=5, ge=1, le=50)
    explanation_max_features: int = Field(default=15, ge=1, le=100)
    explanation_plot_sample_rows: int = Field(default=500, ge=20, le=10_000)
    explanation_learning_curve_rows: int = Field(default=2_000, ge=50, le=50_000)
    random_seed: int = 42
    forecast_max_horizon: int = Field(default=365, ge=1, le=10_000)
    forecast_validation_folds: int = Field(default=3, ge=2, le=10)
    forecast_max_arima_iterations: int = Field(default=50, ge=5, le=500)
    job_stale_after_seconds: int = Field(default=1200, ge=60, le=172_800)
    job_lock_ttl_seconds: int = Field(default=900, ge=60, le=172_800)
    job_max_retries: int = Field(default=2, ge=0, le=10)
    job_min_backoff_ms: int = Field(default=5_000, ge=100, le=600_000)
    job_max_backoff_ms: int = Field(default=60_000, ge=100, le=3_600_000)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

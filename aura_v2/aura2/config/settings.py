"""
Centralized, typed configuration. Every environment variable AURA uses is
declared here, once — no os.getenv() elsewhere. See .env.example for the
full documented list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from utils.errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False,
    )

    # ---- LLM (OpenRouter) ----
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="moonshotai/kimi-k2.6:free", alias="OPENROUTER_MODEL")
    openrouter_fallback_model: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free", alias="OPENROUTER_FALLBACK_MODEL"
    )
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")

    # ---- External tool APIs ----
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    openweather_api_key: str = Field(default="", alias="OPENWEATHER_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")  # Search/YouTube Data API
    google_search_cx: str = Field(default="", alias="GOOGLE_SEARCH_CX")

    # ---- Database (async) ----
    postgres_uri: str = Field(default="postgresql://aura:aura@localhost:5432/aura", alias="POSTGRES_URI")

    # ---- Redis (background jobs) ----
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # ---- Auth ----
    jwt_secret_key: str = Field(default="", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60 * 24 * 7, alias="JWT_EXPIRE_MINUTES")

    # ---- Google OAuth (Gmail, Calendar, Drive) ----
    google_credentials_path: str = Field(default="secrets/google/credentials.json", alias="GOOGLE_CREDENTIALS_PATH")
    google_token_dir: str = Field(default="secrets/google/tokens", alias="GOOGLE_TOKEN_DIR")  # per-user now

    # ---- RAG / embeddings ----
    embedding_model: str = Field(default="intfloat/multilingual-e5-base", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=768, alias="EMBEDDING_DIM")
    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB")
    max_concurrent_ingestion_jobs_per_user: int = Field(default=2, alias="MAX_CONCURRENT_INGESTION_JOBS")

    # ---- Voice ----
    whisper_model_size: str = Field(default="small", alias="WHISPER_MODEL_SIZE")
    voice_enabled: bool = Field(default=False, alias="VOICE_ENABLED")

    # ---- Observability ----
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_project: str = Field(default="aura", alias="LANGSMITH_PROJECT")

    # ---- Runtime safety limits ----
    max_model_calls_per_run: int = Field(default=20, alias="MAX_MODEL_CALLS_PER_RUN")
    max_tool_calls_per_run: int = Field(default=20, alias="MAX_TOOL_CALLS_PER_RUN")
    rate_limit_requests_per_minute: int = Field(default=30, alias="RATE_LIMIT_RPM")

    # ---- Summarization ----
    summarization_trigger_messages: int = Field(default=30, alias="SUMMARIZATION_TRIGGER_MESSAGES")
    summarization_keep_messages: int = Field(default=20, alias="SUMMARIZATION_KEEP_MESSAGES")

    # ---- App ----
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ConfigurationError(f"LOG_LEVEL must be one of {allowed}, got {v!r}")
        return upper

    @model_validator(mode="after")
    def _validate_required(self) -> "Settings":
        missing: list[str] = []
        if not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if not self.postgres_uri:
            missing.append("POSTGRES_URI")
        if not self.jwt_secret_key and self.app_env != "test":
            missing.append("JWT_SECRET_KEY")
        if missing:
            raise ConfigurationError("Missing required environment variables: " + ", ".join(missing))
        return self

    @property
    def google_credentials_exist(self) -> bool:
        return Path(self.google_credentials_path).exists()

    @property
    def tavily_configured(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def google_configured(self) -> bool:
        return bool(self.google_api_key)

    def redacted_summary(self) -> dict:
        return {
            "app_env": self.app_env,
            "openrouter_model": self.openrouter_model,
            "openrouter_fallback_model": self.openrouter_fallback_model,
            "openrouter_configured": bool(self.openrouter_api_key),
            "tavily_configured": self.tavily_configured,
            "google_configured": self.google_configured,
            "google_credentials_configured": self.google_credentials_exist,
            "voice_enabled": self.voice_enabled,
            "langsmith_tracing": self.langsmith_tracing,
            "postgres_configured": bool(self.postgres_uri),
            "redis_configured": bool(self.redis_url),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

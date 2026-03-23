"""GraphIQ — pydantic-settings configuration.

Loads all settings from environment variables / .env file.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment variables.

    All values can be overridden via a `.env` file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────
    postgres_url: str = Field(
        default="postgresql://graphiq:graphiq@localhost:5432/graphiq",
        description="asyncpg-compatible PostgreSQL connection URL",
    )
    neo4j_url: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="")

    # ── LLM providers ───────────────────────────────────────────────────────
    gemini_api_key: str = Field(default="")
    groq_api_key: str = Field(default="")
    openrouter_api_key: str = Field(default="")

    # Comma-separated priority order, e.g. "gemini,groq,openrouter"
    llm_provider_priority: str = Field(default="gemini,groq,openrouter")

    # ── Query limits ─────────────────────────────────────────────────────────
    max_join_depth: int = Field(default=3, ge=1, le=5)
    max_query_limit: int = Field(default=500, ge=1, le=1000)
    max_compound_steps: int = Field(default=3, ge=2, le=3)

    # ── Sync ─────────────────────────────────────────────────────────────────
    sync_interval_seconds: int = Field(default=15, ge=5, le=300)

    # ── Rate limiting ─────────────────────────────────────────────────────────
    rate_limit_per_minute: int = Field(default=30, ge=1)

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    @property
    def provider_priority_list(self) -> list[str]:
        """Return provider names as an ordered list."""
        return [p.strip() for p in self.llm_provider_priority.split(",") if p.strip()]


settings = Settings()

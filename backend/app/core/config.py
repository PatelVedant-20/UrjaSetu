"""Application configuration.

Single source of configuration truth. Everything — the FastAPI app, the
SQLAlchemy engine and Alembic — reads its database settings from here, so the
runtime and the migration tool can never drift apart.

No credentials are hard-coded: `DATABASE_URL` has no default and the process
refuses to start without it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# PostgreSQL is the authoritative operational database (docs/00_PROJECT_BIBLE.md
# section 5). Any other backend — SQLite included — is rejected at startup rather
# than silently producing a system that behaves differently from production.
_ALLOWED_DB_SCHEMES = ("postgresql+psycopg://", "postgresql://")

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Resolved absolutely, not relative to the working directory. Alembic runs from
# `backend/`, uvicorn and pytest from the repo root, and an IDE from anywhere —
# all of them must find the same `.env`. Real environment variables still take
# precedence, so CI and containers are unaffected.
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "UrjaSetu"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # --- Database ----------------------------------------------------------
    database_url: str = Field(..., description="SQLAlchemy URL for the operational database")
    maintenance_database_url: str | None = Field(
        default=None,
        description=(
            "Connection to a maintenance database (normally `postgres`), used only by the "
            "automated migration smoke test to create and drop a throwaway database."
        ),
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    # --- Domain constants (locked; see docs/00_PROJECT_BIBLE.md section 7) ---
    market_mode: str = "day_ahead"

    # Forecast provider used when a request names none. docs/05_API_SPEC.md
    # requires the provider to be chosen by configuration, never hard-coded in
    # a router or service.
    forecast_provider: str = "baseline"

    @field_validator("database_url", "maintenance_database_url")
    @classmethod
    def _must_be_postgresql(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(_ALLOWED_DB_SCHEMES):
            raise ValueError(
                "UrjaSetu requires PostgreSQL. Expected a URL starting with one of "
                f"{_ALLOWED_DB_SCHEMES}, got: {value.split('://', 1)[0]}://..."
            )
        return value

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def enabled_integrations(self) -> list[str]:
        """External adapters wired up in this build.

        Phase 0 intentionally has none: no Power Grid Model, no SunSpec, no
        forecast provider, no ledger. Later phases append as adapters land.
        """
        return []

    def safe_database_url(self) -> str:
        """`database_url` with the password redacted, for logs and error output."""
        return _redact_password(self.database_url)


def _redact_password(url: str) -> str:
    """Replace the password in a URL with `***`.

    Never log or return a connection string without passing it through here
    (docs/00_PROJECT_BIBLE.md section 8).
    """
    scheme_sep = "://"
    if scheme_sep not in url:
        return url
    scheme, rest = url.split(scheme_sep, 1)
    if "@" not in rest:
        return url
    credentials, location = rest.rsplit("@", 1)
    if ":" in credentials:
        user, _ = credentials.split(":", 1)
        credentials = f"{user}:***"
    return f"{scheme}{scheme_sep}{credentials}@{location}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Cached so configuration is parsed and validated once per process. Tests that
    need to change the environment call `get_settings.cache_clear()`.
    """
    return Settings()  # type: ignore[call-arg]

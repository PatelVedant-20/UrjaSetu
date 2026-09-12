"""Alembic environment.

Alembic reads the SAME configuration object as the running application
(docs/09_PHASE_0_SETUP.md Step 8), so the migration tool and the API can never
target different databases, and no connection string is stored in alembic.ini.

Override the target for a single run with:

    alembic -x db_url=postgresql+psycopg://... upgrade head

which is how the automated migration smoke test points at a throwaway database.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# `backend/` on the path so `app.*` imports work regardless of the directory
# alembic was invoked from.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db import models  # noqa: E402,F401  (import registers models on Base.metadata)
from app.db.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate compares the live database against this metadata.
target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the target URL: `-x db_url=...` wins, otherwise app settings."""
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    if override:
        return override
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Catch column type and server-default drift, not just added/dropped
            # tables — otherwise autogenerate silently misses real changes.
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

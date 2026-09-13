"""Idempotently initialize fictional participants without resetting existing data."""

import os

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.experience_service import enable_live
from app.services.workspace_service import bootstrap

if __name__ == "__main__":
    if get_settings().app_env != "development":
        raise SystemExit("Demo bootstrap requires APP_ENV=development.")
    with get_session_factory()() as db:
        created = bootstrap(db, os.environ.get("DEMO_PASSWORD", "Sunshine2026!"))
        enable_live(db)
    print(
        "Demo community created." if created else "Demo community already exists; data preserved."
    )

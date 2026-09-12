"""Fixtures shared by every integration package.

Lives at the integration root so both the lifecycle tests and the realtime
tests can use one definition of a connected client and a committed identity.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.db.models import User
from app.domain.enums import UserRole, UserStatus
from app.main import create_app
from app.services.realtime_service import hub


@pytest.fixture(autouse=True)
def clean_hub() -> Iterator[None]:
    """The hub is process-wide, so each test starts with no subscribers."""
    hub.reset()
    yield
    hub.reset()


@pytest.fixture
def actor(engine: Engine) -> Iterator[User]:
    """An active identity, committed so the gateway can actually see it.

    The WebSocket route resolves identity through its own short-lived session —
    which is right in production and means a user created inside the test's
    rolled-back transaction would be invisible to it. So this one is committed
    for real on its own connection and removed afterwards, leaving the database
    as it was found.
    """
    maker = sessionmaker(bind=engine)
    with maker() as setup:
        user = User(
            display_name="Realtime Client",
            role=UserRole.PROSUMER,
            status=UserStatus.ACTIVE,
            email=f"rt-{uuid.uuid4().hex[:8]}@example.org",
        )
        setup.add(user)
        setup.commit()
        setup.refresh(user)
        setup.expunge(user)

    try:
        yield user
    finally:
        with maker() as teardown:
            teardown.execute(delete(User).where(User.id == user.id))
            teardown.commit()


@pytest.fixture
def suspend_actor(engine: Engine) -> Callable[[User], None]:
    """Suspend the committed actor, visibly to other sessions."""

    def _suspend(user: User) -> None:
        maker = sessionmaker(bind=engine)
        with maker() as s:
            s.execute(update(User).where(User.id == user.id).values(status=UserStatus.SUSPENDED))
            s.commit()

    return _suspend


@pytest.fixture
def ws_client(db_session: Session) -> Iterator[TestClient]:
    """A client whose REST calls share the test's transaction.

    The WebSocket route resolves identity through its own short-lived session,
    which is why `actor` commits: the gateway must be able to see the user.
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()

"""Focused tests for the PostgreSQL Append-Only Hash Chain persistence layer.

Covers Phase 9 requirements:
- Genesis event insertion and querying
- Second event previous-hash linkage
- Duplicate event hash rejection (UniqueConstraint)
- Single genesis constraint (UniqueConstraint on previous_hash with NULLS NOT DISTINCT)
- Fork prevention (UniqueConstraint on previous_hash)
- Non-self-referencing check constraint (event_hash <> previous_hash)
- SHA-256 length check constraints
- Append-only repository enforcement (rejection of delete and update)
- Transaction participation and rollback behavior
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.audit import AuditEventRecord
from app.domain.enums import AuditEntityType, AuditEventType
from app.repositories.audit import AuditAppendOnlyError, AuditEventRepository


def _make_record(
    *,
    event_hash: str,
    previous_hash: str | None = None,
    entity_type: AuditEntityType = AuditEntityType.TRADE,
    entity_id: UUID | None = None,
    event_type: AuditEventType = AuditEventType.TRADE_PROPOSED,
    recorded_at: datetime | None = None,
    payload: dict[str, object] | None = None,
) -> AuditEventRecord:
    now = datetime.now(UTC)
    return AuditEventRecord(
        id=uuid4(),
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id or uuid4(),
        event_time=now,
        recorded_at=recorded_at or now,
        actor_user_id=None,
        payload_json=payload or {"key": "val"},
        event_hash=event_hash,
        previous_hash=previous_hash,
    )


def test_append_persists_to_caller_transaction_without_committing(db_session: Session) -> None:
    """The repository flushes the record inside the caller's transaction without committing."""
    repository = AuditEventRepository(db_session)
    genesis_hash = "a" * 64
    record = _make_record(event_hash=genesis_hash, previous_hash=None)

    appended = repository.append(record)

    assert appended.id == record.id
    # Record is accessible in session
    fetched = repository.get(record.id)
    assert fetched is not None
    assert fetched.event_hash == genesis_hash
    # The session's transaction is still active and uncommitted
    assert db_session.is_active


def test_genesis_event_and_query(db_session: Session) -> None:
    """The genesis event has previous_hash=None and is uniquely identifiable."""
    repository = AuditEventRepository(db_session)
    genesis_hash = "1" * 64
    genesis = _make_record(event_hash=genesis_hash, previous_hash=None)

    repository.append(genesis)

    queried_genesis = repository.genesis()
    assert queried_genesis is not None
    assert queried_genesis.id == genesis.id
    assert queried_genesis.previous_hash is None
    assert queried_genesis.event_hash == genesis_hash

    # Head and latest both point to genesis when it is the only event
    assert repository.head() is not None
    assert repository.head().id == genesis.id
    assert repository.latest().id == genesis.id


def test_second_event_and_previous_hash_linkage(db_session: Session) -> None:
    """A second event successfully links to the genesis event's hash."""
    repository = AuditEventRepository(db_session)
    base_time = datetime.now(UTC)

    genesis_hash = "1" * 64
    second_hash = "2" * 64

    genesis = _make_record(
        event_hash=genesis_hash,
        previous_hash=None,
        recorded_at=base_time,
    )
    repository.append(genesis)

    second = _make_record(
        event_hash=second_hash,
        previous_hash=genesis_hash,
        recorded_at=base_time + timedelta(seconds=1),
    )
    repository.append(second)

    chain = list(repository.list_chain())
    assert len(chain) == 2
    assert chain[0].id == genesis.id
    assert chain[0].previous_hash is None
    assert chain[1].id == second.id
    assert chain[1].previous_hash == genesis_hash

    # Head now points to the second event
    head = repository.head()
    assert head is not None
    assert head.id == second.id
    assert head.event_hash == second_hash


def test_duplicate_event_hash_rejected(db_session: Session) -> None:
    """PostgreSQL rejects inserting two events with identical event_hash."""
    repository = AuditEventRepository(db_session)
    duplicate_hash = "d" * 64

    rec1 = _make_record(event_hash=duplicate_hash, previous_hash=None)
    repository.append(rec1)

    rec2 = _make_record(event_hash=duplicate_hash, previous_hash="e" * 64)
    with pytest.raises(IntegrityError) as exc_info:
        with db_session.begin_nested():
            repository.append(rec2)

    assert "uq_audit_events_event_hash" in str(exc_info.value)


def test_fork_prevention_second_genesis_rejected(db_session: Session) -> None:
    """Single genesis rule: a second event with previous_hash=NULL is rejected."""
    repository = AuditEventRepository(db_session)

    genesis1 = _make_record(event_hash="1" * 64, previous_hash=None)
    repository.append(genesis1)

    genesis2 = _make_record(event_hash="2" * 64, previous_hash=None)
    with pytest.raises(IntegrityError) as exc_info:
        with db_session.begin_nested():
            repository.append(genesis2)

    assert "uq_audit_events_previous_hash" in str(exc_info.value)


def test_fork_prevention_duplicate_previous_hash_rejected(db_session: Session) -> None:
    """No forks: two distinct events cannot claim the same predecessor."""
    repository = AuditEventRepository(db_session)
    genesis_hash = "0" * 64

    genesis = _make_record(event_hash=genesis_hash, previous_hash=None)
    repository.append(genesis)

    branch_a = _make_record(event_hash="a" * 64, previous_hash=genesis_hash)
    repository.append(branch_a)

    branch_b = _make_record(event_hash="b" * 64, previous_hash=genesis_hash)
    with pytest.raises(IntegrityError) as exc_info:
        with db_session.begin_nested():
            repository.append(branch_b)

    assert "uq_audit_events_previous_hash" in str(exc_info.value)


def test_self_referential_hash_rejected(db_session: Session) -> None:
    """An event cannot claim itself as predecessor (event_hash <> previous_hash)."""
    repository = AuditEventRepository(db_session)
    cycle_hash = "c" * 64

    self_ref = _make_record(event_hash=cycle_hash, previous_hash=cycle_hash)
    with pytest.raises(IntegrityError) as exc_info:
        with db_session.begin_nested():
            repository.append(self_ref)

    assert "ck_audit_events_event_does_not_follow_itself" in str(exc_info.value)


def test_hash_length_constraint_enforced(db_session: Session) -> None:
    """Check constraints ensure event_hash is 64 chars and previous_hash is null or 64 chars."""
    repository = AuditEventRepository(db_session)

    # Invalid event_hash length
    short_event_hash = _make_record(event_hash="tooshort", previous_hash=None)
    with pytest.raises(IntegrityError) as exc_info:
        with db_session.begin_nested():
            repository.append(short_event_hash)
    assert "ck_audit_events_event_hash_is_sha256" in str(exc_info.value)

    # Invalid previous_hash length
    short_prev_hash = _make_record(event_hash="a" * 64, previous_hash="bad")
    with pytest.raises(IntegrityError) as exc_info:
        with db_session.begin_nested():
            repository.append(short_prev_hash)
    assert "ck_audit_events_previous_hash_is_sha256" in str(exc_info.value)


def test_append_only_behavior_enforced_by_repository(db_session: Session) -> None:
    """The repository explicitly raises AuditAppendOnlyError on delete or update."""
    repository = AuditEventRepository(db_session)
    record = _make_record(event_hash="e" * 64, previous_hash=None)
    repository.append(record)

    with pytest.raises(AuditAppendOnlyError, match="append-only"):
        repository.delete(record)

    with pytest.raises(AuditAppendOnlyError, match="append-only"):
        repository.update(record)


def test_transaction_rollback(db_session: Session) -> None:
    """If the caller transaction is rolled back, flushed audit records roll back with it."""
    repository = AuditEventRepository(db_session)
    before_count = repository.count()

    savepoint = db_session.begin_nested()
    record = _make_record(event_hash="r" * 64, previous_hash=None)
    repository.append(record)

    assert repository.count() == before_count + 1

    savepoint.rollback()

    assert repository.count() == before_count
    assert repository.get(record.id) is None


def test_timeline_and_entity_reads(db_session: Session) -> None:
    """list_for_entity and get_by_hash retrieve exact records ordered by recorded_at."""
    repository = AuditEventRepository(db_session)
    target_trade_id = uuid4()
    other_trade_id = uuid4()
    now = datetime.now(UTC)

    e1 = _make_record(
        event_hash="1" * 64,
        previous_hash=None,
        entity_type=AuditEntityType.TRADE,
        entity_id=target_trade_id,
        event_type=AuditEventType.TRADE_PROPOSED,
        recorded_at=now,
    )
    e2 = _make_record(
        event_hash="2" * 64,
        previous_hash="1" * 64,
        entity_type=AuditEntityType.TRADE,
        entity_id=other_trade_id,
        event_type=AuditEventType.TRADE_PROPOSED,
        recorded_at=now + timedelta(seconds=1),
    )
    e3 = _make_record(
        event_hash="3" * 64,
        previous_hash="2" * 64,
        entity_type=AuditEntityType.TRADE,
        entity_id=target_trade_id,
        event_type=AuditEventType.TRADE_SETTLED,
        recorded_at=now + timedelta(seconds=2),
    )

    repository.append(e1)
    repository.append(e2)
    repository.append(e3)

    target_timeline = list(repository.list_for_entity(AuditEntityType.TRADE, target_trade_id))
    assert len(target_timeline) == 2
    assert [x.id for x in target_timeline] == [e1.id, e3.id]

    by_hash = repository.get_by_hash("2" * 64)
    assert by_hash is not None
    assert by_hash.id == e2.id

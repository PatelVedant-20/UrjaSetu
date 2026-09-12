"""API contracts for Audit (docs/05_API_SPEC.md).

Transport-layer models only: parse, validate, serialize.
No hashing, chain linking, or cryptography inside schemas.
All integrity guarantees are owned by app.domain.policies.audit_chain
and app.services.audit_service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AuditEntityType, AuditEventType


class AuditEventRead(BaseModel):
    """`GET /audit/entities/{entity_type}/{entity_id}` item and anchor response body.

    Serializes stored AuditEventRecord (Entity 21 of docs/04_DATA_MODEL.md).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: AuditEventType
    entity_type: AuditEntityType
    entity_id: UUID
    event_time: datetime
    recorded_at: datetime
    actor_user_id: UUID | None = None
    payload_json: dict[str, Any]
    event_hash: str = Field(..., description="SHA-256 hash over canonical event content")
    previous_hash: str | None = Field(
        default=None,
        description="Hash of previous event in chain (NULL for genesis)",
    )
    ledger_anchor_id: str | None = Field(
        default=None,
        description="External DLT anchor receipt reference if published",
    )


class ChainVerificationRead(BaseModel):
    """Serializes canonical ChainVerification contract."""

    model_config = ConfigDict(from_attributes=True)

    intact: bool = Field(..., description="True if cryptographic chain is completely valid")
    events_checked: int = Field(..., description="Count of evaluated events in chain")
    broken_at_event_id: UUID | None = Field(
        default=None,
        description="Event ID where hash linkage failed, if any",
    )
    problems: list[str] = Field(
        default_factory=list,
        description="Diagnostic explanations of verification failures",
    )
    summary: str = Field(..., description="Human-readable chain summary")


class LedgerAnchorRead(BaseModel):
    """Serializes canonical LedgerAnchor receipt contract."""

    model_config = ConfigDict(from_attributes=True)

    reference: str = Field(..., description="Publisher receipt reference")
    publisher: str = Field(..., description="Identifier of the ledger adapter")
    published_at: datetime = Field(..., description="Timestamp when evidence was published")

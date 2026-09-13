"""Identity, simulation clock and delivery evidence for the connected marketplace."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LoginCredential(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "login_credentials"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)


class LoginSession(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "login_sessions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Simulation(Base, TimestampMixin):
    __tablename__ = "simulation_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    clock: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    running: Mapped[bool] = mapped_column(default=False)
    scenario: Mapped[str] = mapped_column(String(32), default="normal")
    revision: Mapped[int] = mapped_column(default=0)
    weather: Mapped[dict] = mapped_column(JSONB, default=dict)
    live_mode: Mapped[bool] = mapped_column(default=False, server_default="false")


class HouseholdProfile(Base, TimestampMixin):
    __tablename__ = "household_profiles"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    avatar: Mapped[str | None] = mapped_column(Text)
    photo: Mapped[str | None] = mapped_column(Text)


class MarketplaceAction(Base, TimestampMixin):
    __tablename__ = "marketplace_actions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    trade_id: Mapped[UUID] = mapped_column(ForeignKey("trades.id"))


class TradeAllocation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "trade_allocations"
    trade_id: Mapped[UUID] = mapped_column(ForeignKey("trades.id"), unique=True)
    seller_reading_id: Mapped[UUID] = mapped_column(ForeignKey("telemetry_readings.id"))
    buyer_reading_id: Mapped[UUID] = mapped_column(ForeignKey("telemetry_readings.id"))
    energy_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 4))


class Receipt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Durable publication job and independently verifiable EVM receipt."""

    __tablename__ = "blockchain_receipts"
    trade_id: Mapped[UUID] = mapped_column(ForeignKey("trades.id"), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    transaction_hash: Mapped[str | None] = mapped_column(String(66))
    block_number: Mapped[int | None]
    chain_id: Mapped[int | None]
    contract_address: Mapped[str | None] = mapped_column(String(42))
    error: Mapped[str | None] = mapped_column(Text)


class JournalEntry(Base, UUIDPrimaryKeyMixin):
    """Signed account postings; sum for each settlement is exactly zero."""

    __tablename__ = "journal_entries"
    settlement_id: Mapped[UUID] = mapped_column(ForeignKey("settlements.id"))
    account: Mapped[str] = mapped_column(String(100))
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    __table_args__ = (UniqueConstraint("settlement_id", "account"),)

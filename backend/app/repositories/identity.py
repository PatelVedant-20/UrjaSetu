"""Repositories for the identity module."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from app.db.models.identity import Consent, User, UtilityAccount
from app.domain.enums import ConsentScope
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.session.execute(stmt).scalar_one_or_none()


class UtilityAccountRepository(BaseRepository[UtilityAccount]):
    model = UtilityAccount

    def list_for_user(self, user_id: UUID) -> Sequence[UtilityAccount]:
        stmt = select(UtilityAccount).where(UtilityAccount.user_id == user_id)
        return self.session.execute(stmt).scalars().all()

    def get_by_consumer_number_hash(
        self, discom_code: str, consumer_number_hash: str
    ) -> UtilityAccount | None:
        """Look up the account a DISCOM consumer number belongs to.

        The pair is unique, so this either resolves or the connection is
        unclaimed.
        """
        stmt = select(UtilityAccount).where(
            UtilityAccount.discom_code == discom_code,
            UtilityAccount.consumer_number_hash == consumer_number_hash,
        )
        return self.session.execute(stmt).scalar_one_or_none()


class ConsentRepository(BaseRepository[Consent]):
    model = Consent

    def list_for_user(self, user_id: UUID) -> Sequence[Consent]:
        stmt = select(Consent).where(Consent.user_id == user_id)
        return self.session.execute(stmt).scalars().all()

    def list_active_for_user(self, user_id: UUID) -> Sequence[Consent]:
        """Grants that have not been revoked.

        Revocation is a timestamp, not a deletion, so "active" is a query
        rather than the absence of a row.
        """
        stmt = select(Consent).where(
            Consent.user_id == user_id,
            Consent.revoked_at.is_(None),
        )
        return self.session.execute(stmt).scalars().all()

    def has_active_scope(self, user_id: UUID, scope: ConsentScope) -> bool:
        stmt = select(Consent.id).where(
            Consent.user_id == user_id,
            Consent.scope == scope,
            Consent.revoked_at.is_(None),
        )
        return self.session.execute(stmt).first() is not None

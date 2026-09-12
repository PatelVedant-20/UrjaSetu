"""Shared SQLAlchemy column types and conventions.

Keeps persistence-level decisions in one place so every model spells the same
concept the same way.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """A native PostgreSQL enum type backed by a domain `StrEnum`.

    Two details matter and are easy to get wrong:

    * `values_callable` — without it SQLAlchemy persists the member *names*
      (`CONSUMER`), not the values (`consumer`). The data model and the API
      contract both speak in lowercase values, so the database must too.
    * `native_enum=True` — the constraint is enforced by a real PostgreSQL type
      rather than by application code, which is what
      docs/04_DATA_MODEL.md requires of integrity rules.

    Adding a member later is an `ALTER TYPE ... ADD VALUE` migration. Removing
    or renaming one is a breaking change and needs a data migration.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )

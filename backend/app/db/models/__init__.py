"""Persistence models.

Importing every model here is what populates `Base.metadata`, which is what
Alembic autogenerate compares against the live database. A model that is not
reachable from this module is invisible to migrations.
"""

from app.db.models.system_metadata import SystemMetadata

__all__ = ["SystemMetadata"]

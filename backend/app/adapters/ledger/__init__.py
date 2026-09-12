"""Ledger adapters — the only place a DLT library may ever be imported.

docs/06_OPEN_SOURCE_INTEGRATION.md lists Hyperledger Fabric as an *optional
later* audit layer and FireFly as deferred. Nothing in this package is required
for UrjaSetu to run: with no publisher configured, audit events are recorded in
PostgreSQL and verified there, which is the documented source of truth.
"""

from app.adapters.ledger.local_publisher import LocalFilePublisher

__all__ = ["LocalFilePublisher"]

"""Managed background task: simulation advancement, public weather and EVM outbox."""

import asyncio
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.adapters.ledger.evm import publish
from app.db.models import Receipt, Simulation
from app.db.session import get_engine
from app.services.workspace_service import advance, bump, state

logger = logging.getLogger(__name__)


def refresh_weather(db: Session) -> None:
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 23.0225,
                "longitude": 72.5714,
                "current": "temperature_2m,cloud_cover,shortwave_radiation",
                "timezone": "UTC",
            },
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        weather = {
            "status": "available",
            "current": data["current"],
            "units": data["current_units"],
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "Open-Meteo weather model",
            "note": (
                "Present real-world weather context; not measured rooftop output "
                "or simulation-time weather."
            ),
        }
    except Exception as exc:
        weather = {
            "status": "unavailable",
            "error": type(exc).__name__,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
    sim = state(db, True)
    sim.weather = weather
    bump(sim)
    db.commit()


def cycle(weather: bool = False) -> None:
    with get_engine().connect() as connection, Session(bind=connection) as db:
        # Session-level advisory lock elects one active worker across API processes.
        if not db.scalar(text("SELECT pg_try_advisory_lock(8675309)")):
            return
        try:
            sim = db.get(Simulation, 1)
            if not sim:
                return
            if sim.live_mode:
                from app.services.experience_service import tick

                tick(db)
            elif sim.running:
                advance(db)
            if weather:
                refresh_weather(db)
            pending = list(
                db.scalars(select(Receipt).where(Receipt.status != "confirmed").limit(10))
            )
            for receipt in pending:
                try:
                    publish(receipt)
                except Exception as exc:
                    receipt.status, receipt.error = "pending", str(exc)[:300]
                bump(state(db, True))
                db.commit()
        finally:
            db.execute(text("SELECT pg_advisory_unlock(8675309)"))
            db.commit()


async def run_worker() -> None:
    count = 0
    while True:
        try:
            await asyncio.to_thread(cycle, count % 180 == 0)
        except Exception:
            logger.exception("Workspace worker cycle failed; retrying")
        count += 1
        await asyncio.sleep(5)

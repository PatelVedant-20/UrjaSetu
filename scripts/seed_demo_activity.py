#!/usr/bin/env python3
"""Seed multi-user realistic demo activity into UrjaSetu.

Creates a vibrant community microgrid with multiple prosumers and consumers:
- Asha Patel (prosumer, 6.0 kW)
- Ravi Shah (consumer)
- Priya Sharma (prosumer, 7.5 kW)
- Vikram Mehta (prosumer, 6.0 kW)
- Kavita Desai (prosumer, 8.0 kW)
- Ananya Joshi (consumer)
- Deepak Verma (consumer)
- Rajesh Kumar (consumer)

Generates:
1. Multi-counterparty P2P trades across different neighbors
2. Real two-sided Order Book depth on the Marketplace
3. Reconciled meter settlements with financial journal entries
4. On-chain confirmed EVM blockchain receipts

Run from repo root with:
    PYTHONPATH=backend .venv/bin/python scripts/seed_demo_activity.py
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed_demo_activity")

D = Decimal

COMMUNITY_PERSONAS: list[dict[str, Any]] = [
    {
        "email": "priya@urjasetu.demo",
        "name": "Priya Sharma",
        "role": "prosumer",
        "pv_kw": 7.5,
        "setup": {
            "city": "Ahmedabad",
            "home_type": "independent",
            "occupants": 3,
            "monthly_kwh": 320,
            "ac_count": 2,
            "has_ev": True,
            "daytime_home": False,
            "orientation": "south",
            "tilt": 23,
            "retail_rate": 7.0,
            "share_stats": True,
        },
    },
    {
        "email": "vikram@urjasetu.demo",
        "name": "Vikram Mehta",
        "role": "prosumer",
        "pv_kw": 6.0,
        "setup": {
            "city": "Gandhinagar",
            "home_type": "semi_detached",
            "occupants": 4,
            "monthly_kwh": 380,
            "ac_count": 1,
            "has_ev": True,
            "daytime_home": True,
            "orientation": "south",
            "tilt": 23,
            "retail_rate": 7.0,
            "share_stats": True,
        },
    },
    {
        "email": "kavita@urjasetu.demo",
        "name": "Kavita Desai",
        "role": "prosumer",
        "pv_kw": 8.0,
        "setup": {
            "city": "Surat",
            "home_type": "villa",
            "occupants": 5,
            "monthly_kwh": 450,
            "ac_count": 3,
            "has_ev": False,
            "daytime_home": True,
            "orientation": "south",
            "tilt": 23,
            "retail_rate": 7.0,
            "share_stats": True,
        },
    },
    {
        "email": "ananya@urjasetu.demo",
        "name": "Ananya Joshi",
        "role": "consumer",
        "pv_kw": 0,
        "setup": {
            "city": "Ahmedabad",
            "home_type": "apartment",
            "occupants": 3,
            "monthly_kwh": 290,
            "ac_count": 2,
            "has_ev": False,
            "daytime_home": False,
            "orientation": "south",
            "tilt": 23,
            "retail_rate": 7.0,
            "share_stats": True,
        },
    },
    {
        "email": "deepak@urjasetu.demo",
        "name": "Deepak Verma",
        "role": "consumer",
        "pv_kw": 0,
        "setup": {
            "city": "Vadodara",
            "home_type": "apartment",
            "occupants": 2,
            "monthly_kwh": 240,
            "ac_count": 1,
            "has_ev": False,
            "daytime_home": True,
            "orientation": "south",
            "tilt": 23,
            "retail_rate": 7.0,
            "share_stats": True,
        },
    },
    {
        "email": "rajesh@urjasetu.demo",
        "name": "Rajesh Kumar",
        "role": "consumer",
        "pv_kw": 0,
        "setup": {
            "city": "Ahmedabad",
            "home_type": "row_house",
            "occupants": 4,
            "monthly_kwh": 350,
            "ac_count": 1,
            "has_ev": False,
            "daytime_home": True,
            "orientation": "south",
            "tilt": 23,
            "retail_rate": 7.0,
            "share_stats": True,
        },
    },
]


def main() -> None:
    from sqlalchemy import func, select

    from app.db.models import (
        ForecastPoint,
        ForecastRun,
        Order,
        Receipt,
        Settlement,
        Site,
        Trade,
        User,
    )
    from app.db.session import get_session_factory
    from app.domain.enums import OrderSide, OrderStatus, TradeStatus
    from app.domain.policies.community_energy import INTERVAL, IST
    from app.services import workspace_service as ws

    Session = get_session_factory()
    db = Session()

    # ── 1. Load or Register Community Users ───────────────────────────────
    sim = ws.state(db, True)
    users_by_email = {u.email: u for u in db.execute(select(User)).scalars()}

    for persona in COMMUNITY_PERSONAS:
        email = persona["email"]
        if email not in users_by_email:
            log.info("Registering community neighbor %s (%s)…", persona["name"], persona["role"])
            try:
                user = ws.register(
                    db,
                    sim,
                    email=email,
                    password="Sunshine2026!",
                    name=persona["name"],
                    role=persona["role"],
                    pv_kw=Decimal(str(persona["pv_kw"] or 1)),
                    setup=persona["setup"],
                )
                db.commit()
                users_by_email[email] = user
            except Exception as e:
                log.warning("Registration failed for %s: %s", email, e)
                db.rollback()

    users = {u.email: u for u in db.execute(select(User)).scalars()}
    log.info("Total community members in database: %d", len(users))

    asha = users["asha@urjasetu.demo"]
    ravi = users["ravi@urjasetu.demo"]
    priya = users.get("priya@urjasetu.demo")
    vikram = users.get("vikram@urjasetu.demo")
    kavita = users.get("kavita@urjasetu.demo")
    ananya = users.get("ananya@urjasetu.demo")
    deepak = users.get("deepak@urjasetu.demo")
    rajesh = users.get("rajesh@urjasetu.demo")

    # ── 2. Cancel stale open orders so order book is clean ────────────────
    stale = list(
        db.scalars(
            select(Order).where(Order.status.in_([OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]))
        )
    )
    for order in stale:
        order.status = OrderStatus.CANCELLED
    if stale:
        log.info("Cancelled %d stale open orders.", len(stale))
    db.commit()

    # ── 3. Ensure forecasts exist for all community sites tomorrow ────────
    tomorrow = (
        (sim.clock.astimezone(IST) + timedelta(days=1))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )
    for site in ws.sites(db):
        has_fc = db.scalar(
            select(ForecastPoint.id)
            .join(ForecastRun)
            .where(
                ForecastPoint.site_id == site.id,
                ForecastPoint.interval_start >= tomorrow,
                ForecastPoint.interval_start < tomorrow + timedelta(days=1),
            )
            .limit(1)
        )
        if not has_fc:
            ws.forecast(db, site, sim)
    db.commit()

    available_slots = list(
        db.scalars(
            select(ForecastPoint.interval_start)
            .join(ForecastRun)
            .where(
                ForecastPoint.interval_start >= tomorrow,
                ForecastPoint.interval_start < tomorrow + timedelta(days=1),
            )
            .distinct()
            .order_by(ForecastPoint.interval_start)
        )
    )
    slot_map = {s.astimezone(IST).strftime("%H:%M"): s for s in available_slots}

    # ── 4. Create Multi-Counterparty P2P Trades ───────────────────────────
    # Broad pricing limits allow the dynamic tariff engine to clear at fair rates.
    trade_plan = [
        # Asha selling to multiple different buyers:
        (asha, ravi, "10:00", D("0.30")),
        (asha, ananya, "10:30", D("0.30")),
        (asha, deepak, "11:15", D("0.30")),
        (asha, rajesh, "11:30", D("0.30")),
        (asha, ananya, "12:00", D("0.30")),
        (asha, deepak, "12:15", D("0.30")),
        (asha, rajesh, "12:45", D("0.30")),
        (asha, ravi, "13:00", D("0.30")),
        # Ravi buying from multiple different solar prosumers:
        (priya, ravi, "10:15", D("0.40")),
        (vikram, ravi, "10:45", D("0.35")),
        (kavita, ravi, "11:15", D("0.45")),
        (priya, ravi, "12:15", D("0.35")),
        (vikram, ravi, "13:15", D("0.35")),
        # Other community prosumers trading with other consumers:
        (priya, ananya, "11:00", D("0.35")),
        (vikram, deepak, "11:45", D("0.30")),
        (kavita, rajesh, "12:00", D("0.40")),
        (kavita, ananya, "12:30", D("0.35")),
        (vikram, rajesh, "12:45", D("0.30")),
        (priya, deepak, "13:00", D("0.35")),
        (kavita, deepak, "13:30", D("0.40")),
    ]

    trades_created = 0
    for seller, buyer, ist_str, req_kwh in trade_plan:
        if seller is None or buyer is None:
            continue
        slot = slot_map.get(ist_str)
        if not slot:
            continue

        site = db.scalar(select(Site).where(Site.owner_user_id == seller.id))
        if not site:
            continue

        try:
            basis = ws.prediction(db, site.id, slot)
            solar_kwh, load_kwh = basis["solar"].predicted_kwh, basis["load"].predicted_kwh
            available_kwh = max(D(0), (solar_kwh or D(0)) - (load_kwh or D(0)))

            reserved = sum(
                (
                    x.matched_kwh + (x.remaining_kwh if x.status.is_active else D(0))
                    for x in ws.rows(
                        db,
                        Order,
                        Order.site_id == site.id,
                        Order.delivery_start == slot,
                        Order.side == OrderSide.SELL,
                    )
                ),
                D(0),
            )
            free_surplus = max(D(0), available_kwh - reserved)
            if free_surplus < D("0.10"):
                continue

            kwh = min(req_kwh, (free_surplus * D("0.85")).quantize(D("0.0001")))
            if kwh < D("0.05"):
                continue

            sell_order = ws.place_order(db, seller, slot, "sell", kwh, D("4.50"), commit=False)
            buy_order = ws.place_order(db, buyer, slot, "buy", kwh, D("8.00"), commit=False)
            matched_trades = ws.clear_market(db, order_ids={sell_order.id, buy_order.id}, commit=False)
            committed = [t for t in matched_trades if t.status == TradeStatus.COMMITTED]
            if committed:
                trades_created += len(committed)
                log.info(
                    "  [TRADE] %s IST: %s -> %s (%.4f kWh @ ₹%.2f)",
                    ist_str, seller.display_name, buyer.display_name,
                    committed[0].quantity_kwh, committed[0].clearing_price_inr_per_kwh,
                )
                db.commit()
            else:
                db.rollback()
        except Exception as exc:
            db.rollback()
            log.debug("  Slot %s trade skipped: %s", ist_str, exc)

    log.info("Total newly committed cross-counterparty trades: %d", trades_created)

    # ── 5. Populate Active Marketplace Order Book (Bids & Asks) ───────────
    # Price spread (asks: 6.50–6.80, bids: 5.60–6.00) prevents execution,
    # ensuring full, live order book depth visible across all accounts!
    order_book_plan = [
        # Asks from prosumers:
        (asha, "13:45", "sell", D("0.35"), D("6.60")),
        (priya, "13:45", "sell", D("0.45"), D("6.50")),
        (vikram, "14:00", "sell", D("0.40"), D("6.70")),
        (kavita, "14:00", "sell", D("0.55"), D("6.45")),
        (asha, "14:15", "sell", D("0.30"), D("6.65")),
        (priya, "14:30", "sell", D("0.40"), D("6.55")),
        (vikram, "14:45", "sell", D("0.35"), D("6.75")),
        (kavita, "15:00", "sell", D("0.50"), D("6.40")),
        (asha, "15:15", "sell", D("0.25"), D("6.80")),
        (priya, "15:30", "sell", D("0.30"), D("6.60")),
        (kavita, "15:45", "sell", D("0.40"), D("6.50")),
        (vikram, "16:00", "sell", D("0.30"), D("6.70")),
        # Bids from consumers:
        (ravi, "13:45", "buy", D("0.40"), D("5.90")),
        (ananya, "13:45", "buy", D("0.35"), D("5.80")),
        (deepak, "14:00", "buy", D("0.30"), D("5.70")),
        (rajesh, "14:00", "buy", D("0.45"), D("5.95")),
        (ravi, "14:15", "buy", D("0.35"), D("6.00")),
        (ananya, "14:30", "buy", D("0.40"), D("5.85")),
        (deepak, "14:45", "buy", D("0.25"), D("5.65")),
        (rajesh, "15:00", "buy", D("0.40"), D("5.90")),
        (ravi, "15:15", "buy", D("0.30"), D("5.80")),
        (ananya, "15:30", "buy", D("0.35"), D("5.75")),
        (deepak, "15:45", "buy", D("0.30"), D("5.70")),
        (rajesh, "16:00", "buy", D("0.35"), D("5.85")),
    ]

    open_orders_added = 0
    for user, ist_str, side, req_kwh, price in order_book_plan:
        if user is None:
            continue
        slot = slot_map.get(ist_str)
        if not slot:
            continue
        try:
            if side == "sell":
                site = db.scalar(select(Site).where(Site.owner_user_id == user.id))
                basis = ws.prediction(db, site.id, slot)
                solar_kwh, load_kwh = basis["solar"].predicted_kwh, basis["load"].predicted_kwh
                avail = max(D(0), (solar_kwh or D(0)) - (load_kwh or D(0)))
                res = sum(
                    (
                        x.matched_kwh + (x.remaining_kwh if x.status.is_active else D(0))
                        for x in ws.rows(
                            db,
                            Order,
                            Order.site_id == site.id,
                            Order.delivery_start == slot,
                            Order.side == OrderSide.SELL,
                        )
                    ),
                    D(0),
                )
                free = max(D(0), avail - res)
                if free < D("0.08"):
                    continue
                kwh = min(req_kwh, (free * D("0.85")).quantize(D("0.0001")))
                if kwh < D("0.05"):
                    continue
            else:
                kwh = req_kwh

            ws.place_order(db, user, slot, side, kwh, price, commit=False)
            open_orders_added += 1
            db.commit()
        except Exception:
            db.rollback()

    log.info("Added %d open offers to Marketplace Order Book.", open_orders_added)

    # ── 6. Advance Simulation to Reconcile & Settle Delivered Trades ──────
    due_trades = list(db.scalars(select(Trade).where(Trade.status == TradeStatus.COMMITTED)))
    if due_trades:
        log.info("Advancing simulation to deliver and reconcile %d committed trades…", len(due_trades))
        try:
            sim = ws.advance(db, deliver=True)
            log.info("Simulation clock advanced to: %s", sim.clock)
        except Exception as exc:
            log.warning("deliver advance failed (%s), advancing in chunks…", exc)
            target = max(t.delivery_end for t in due_trades)
            while sim.clock < target:
                chunk = min(96, max(1, int((target - sim.clock) / INTERVAL)))
                sim = ws.advance(db, intervals=chunk)
            log.info("Simulation clock reached: %s", sim.clock)

    # ── 7. Publish Cryptographic Receipts to EVM Blockchain ───────────────
    pending = list(db.scalars(select(Receipt).where(Receipt.status != "confirmed")))
    log.info("Receipts awaiting on-chain confirmation: %d", len(pending))
    if pending:
        try:
            from app.adapters.ledger.evm import publish

            confirmed_now = 0
            for receipt in pending:
                try:
                    publish(receipt)
                    confirmed_now += 1
                except Exception as exc:
                    receipt.status = "pending"
                    receipt.error = str(exc)[:300]
            ws.bump(ws.state(db, True))
            db.commit()
            log.info("Published and confirmed %d/%d receipts on EVM blockchain.", confirmed_now, len(pending))
        except Exception as exc:
            log.warning("Blockchain publish failed: %s", exc)

    # ── 8. Final System Summary ───────────────────────────────────────────
    order_count = db.scalar(select(func.count()).select_from(Order))
    open_order_count = db.scalar(
        select(func.count()).select_from(Order).where(Order.status.in_([OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]))
    )
    trade_count = db.scalar(select(func.count()).select_from(Trade))
    settlement_count = db.scalar(select(func.count()).select_from(Settlement))
    receipt_count = db.scalar(select(func.count()).select_from(Receipt))
    confirmed_receipts = db.scalar(select(func.count()).select_from(Receipt).where(Receipt.status == "confirmed"))

    log.info("════════════════════════════════════════════════════")
    log.info("  UrjaSetu Community Seeding Summary:")
    log.info("    Total Users:              %d", len(users))
    log.info("    Total Orders in System:   %d", order_count)
    log.info("    Live Marketplace Offers:  %d", open_order_count)
    log.info("    Total Executed Trades:    %d", trade_count)
    log.info("    Reconciled Settlements:   %d", settlement_count)
    log.info("    Blockchain Receipts:      %d (%d confirmed on-chain)", receipt_count, confirmed_receipts)
    log.info("════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()

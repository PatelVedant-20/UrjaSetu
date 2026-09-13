"""Shared household analytics, wall-clock telemetry and community projections."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import HouseholdProfile, Meter, Order, Site, TelemetryReading, User
from app.domain.policies.community_energy import INTERVAL, IST
from app.domain.policies.household_energy import DEFAULTS, VERSION, power
from app.services import workspace_service as ws

PERIODS = {
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}
CHANNELS = ("generation_kwh", "load_kwh", "grid_import_kwh", "grid_export_kwh")


def floor_time(moment: datetime, seconds: int) -> datetime:
    return datetime.fromtimestamp(int(moment.timestamp()) // seconds * seconds, UTC)


def now(db: Session) -> datetime:
    sim = ws.state(db)
    return floor_time(datetime.now(UTC) if sim.live_mode else sim.clock, 5)


def save_profile(db: Session, user: User, setup: dict[str, Any]) -> None:
    sim = ws.state(db, True)
    row = db.get(HouseholdProfile, user.id)
    if row is None:
        row = HouseholdProfile(user_id=user.id)
        db.add(row)
    row.settings = {k: v for k, v in setup.items() if k not in ("avatar", "photo")}
    row.avatar, row.photo = setup.get("avatar"), setup.get("photo")
    ws.bump(sim)
    db.commit()


def enable_live(db: Session) -> None:
    """One-time upgrade preserves existing readings, orders and ledger evidence."""
    sim = ws.state(db, True)
    sim.clock = floor_time(datetime.now(UTC), 900)
    sim.live_mode, sim.running, sim.scenario = True, False, "normal"
    for site in ws.sites(db):
        if not db.get(HouseholdProfile, site.owner_user_id):
            db.add(HouseholdProfile(user_id=site.owner_user_id, settings=dict(DEFAULTS)))
    db.flush()
    for site in ws.sites(db):
        ws.add_readings(db, site, [sim.clock - INTERVAL * i for i in range(30 * 96, 0, -1)])
        db.flush()
        ws.forecast(db, site, sim)
    ws.bump(sim)
    db.commit()


def tick(db: Session) -> None:
    sim = ws.state(db, True)
    end = floor_time(datetime.now(UTC), 900)
    start = min(end, max(sim.clock, end - timedelta(days=30)))
    moments = [start + INTERVAL * i for i in range(int((end - start) / INTERVAL))]
    for site in ws.sites(db):
        ws.add_readings(db, site, moments)
    sim.clock = end
    db.flush()
    ws.reconcile_due(db, sim)
    if moments:
        for site in ws.sites(db):
            ws.forecast(db, site, sim)
    ws.bump(sim)
    db.commit()


def aggregates(
    db: Session, end: datetime
) -> tuple[dict[str, dict[str, dict[str, float]]], dict[str, list[dict[str, Any]]]]:
    totals: dict[str, dict[str, dict[str, float]]] = {}
    for period, duration in PERIODS.items():
        query = (
            select(Site.owner_user_id, *(func.sum(getattr(TelemetryReading, c)) for c in CHANNELS))
            .join(Meter, Meter.site_id == Site.id)
            .join(TelemetryReading, TelemetryReading.meter_id == Meter.id)
            .where(
                TelemetryReading.interval_start >= end - duration,
                TelemetryReading.interval_end <= end,
                TelemetryReading.quality_status == "valid",
            )
            .group_by(Site.owner_user_id)
        )
        for row in db.execute(query):
            totals.setdefault(str(row[0]), {})[period] = {
                key: round(float(row[i + 1] or 0), 4) for i, key in enumerate(CHANNELS)
            }
    day = func.date(func.timezone("Asia/Kolkata", TelemetryReading.interval_start))
    query = (
        select(Site.owner_user_id, day, *(func.sum(getattr(TelemetryReading, c)) for c in CHANNELS))
        .join(Meter, Meter.site_id == Site.id)
        .join(TelemetryReading, TelemetryReading.meter_id == Meter.id)
        .where(
            TelemetryReading.interval_start >= end - PERIODS["month"],
            TelemetryReading.interval_end <= end,
            TelemetryReading.quality_status == "valid",
        )
        .group_by(Site.owner_user_id, day)
        .order_by(day)
    )
    daily: dict[str, list[dict[str, Any]]] = {}
    for row in db.execute(query):
        daily.setdefault(str(row[0]), []).append(
            {
                "date": str(row[1]),
                **{key: round(float(row[i + 2] or 0), 4) for i, key in enumerate(CHANNELS)},
            }
        )
    return totals, daily


def dashboard(db: Session, user: User) -> dict[str, Any]:
    data = ws.snapshot(db, user)
    end = now(db)
    profiles = {str(p.user_id): p for p in ws.rows(db, HouseholdProfile)}
    household_sites = {str(s.owner_user_id): s for s in ws.sites(db)}
    totals, daily = aggregates(db, floor_time(end, 900))
    members = []
    for member in data["community"]:
        uid = str(member["id"])
        profile = profiles.get(uid)
        setup = DEFAULTS | (profile.settings if profile else {})
        site = household_sites.get(uid)
        cap = float(ws.capacity(db, site)) if site else 0
        member_stats = totals.get(uid, {})
        shared = setup["share_stats"] or uid == str(user.id)
        members.append(
            {
                **member,
                "avatar": profile.avatar if profile else None,
                "photo": profile.photo if profile else None,
                "city": setup["city"],
                "home_type": setup["home_type"],
                "capacity_kw": cap,
                "node_id": site.grid_node_id if site else None,
                "joined_at": profile.created_at if profile else None,
                "sharing": setup["share_stats"],
                "periods": member_stats if shared else None,
                "daily": daily.get(uid, []) if shared else [],
                "live": power(end, cap, setup, uid) if shared and site else None,
            }
        )
    own = profiles.get(str(user.id))
    settings = DEFAULTS | (own.settings if own else {})
    periods = totals.get(str(user.id), {})
    settlements = data["settlements"]
    for name, duration in PERIODS.items():
        stats = periods.setdefault(name, dict.fromkeys(CHANNELS, 0.0))
        settled = [r for r in settlements if end - duration <= r["settled_at"] <= end]
        purchases = [r for r in settled if r["buyer_user_id"] == user.id]
        sales = [r for r in settled if r["seller_user_id"] == user.id]
        stats.update(
            bought_kwh=sum(float(r["settled_kwh"]) for r in purchases),
            sold_kwh=sum(float(r["settled_kwh"]) for r in sales),
            spent_inr=sum(float(r["buyer_debit_inr"]) for r in purchases),
            earned_inr=sum(float(r["seller_credit_inr"]) for r in sales),
        )
        stats["solar_savings_inr"] = max(
            0, stats["generation_kwh"] - stats["grid_export_kwh"]
        ) * float(settings["retail_rate"])
        stats["trade_savings_inr"] = (
            stats["bought_kwh"] * float(settings["retail_rate"]) - stats["spent_inr"]
        )
        stats["savings_inr"] = stats["solar_savings_inr"] + stats["trade_savings_inr"]
        stats["traded_kwh"] = stats["bought_kwh"] + stats["sold_kwh"]
    own_daily = daily.get(str(user.id), [])
    for point in own_daily:
        selected = [
            r for r in settlements if str(r["settled_at"].astimezone(IST).date()) == point["date"]
        ]
        point["earned_inr"] = sum(
            float(r["seller_credit_inr"]) for r in selected if r["seller_user_id"] == user.id
        )
        point["spent_inr"] = sum(
            float(r["buyer_debit_inr"]) for r in selected if r["buyer_user_id"] == user.id
        )
        bought = sum(float(r["settled_kwh"]) for r in selected if r["buyer_user_id"] == user.id)
        point["savings_inr"] = (
            max(0, point["generation_kwh"] - point["grid_export_kwh"]) + bought
        ) * float(settings["retail_rate"]) - point["spent_inr"]
    order_owners = {o.id: str(o.user_id) for o in ws.rows(db, Order)}
    names = {str(m["id"]): m["name"] for m in members}
    for offer in data["order_book"]:
        uid = order_owners[offer["id"]]
        offer.update(
            user_id=uid,
            owner_name=names.get(uid, "Household"),
            avatar=profiles[uid].avatar if uid in profiles else None,
        )
    for table, key in (
        ("orders", "created_at"),
        ("trades", "created_at"),
        ("settlements", "settled_at"),
        ("receipts", "created_at"),
        ("audit", "recorded_at"),
    ):
        data[table].sort(key=lambda row: (str(row.get(key, "")), str(row["id"])), reverse=True)
    data["order_book"].sort(
        key=lambda row: (
            str(row["delivery_start"]),
            float(row["price"]) * (1 if row["side"] == "sell" else -1),
            str(row["id"]),
        )
    )
    data.update(
        as_of=end,
        members=members,
        profile={
            **settings,
            "avatar": own.avatar if own else None,
            "photo": own.photo if own else None,
        },
        periods=periods,
        daily=own_daily,
        live=next((m["live"] for m in members if m["id"] == user.id), None),
        data_connection={
            "kind": "profile_based",
            "meter_connected": False,
            "model_version": VERSION,
        },
        refresh_seconds=5,
    )
    return data


def series(db: Session, user: User, scope: str, window: str, resolution: str) -> dict[str, Any]:
    end = now(db)
    seconds = {"5s": 5, "1m": 60, "15m": 900}[resolution]
    duration = {"live": 900, "hour": 3600, "day": 86400}[window]
    if duration // seconds > 1800:
        raise HTTPException(422, "Use one-minute or 15-minute readings for the last 24 hours.")
    selected = [s for s in ws.sites(db) if scope == "community" or s.owner_user_id == user.id]
    end = floor_time(end, seconds)
    # 15-minute history is read from persisted interval energy. Faster views use
    # the versioned household model; they are indicative power, never settlement evidence.
    if resolution == "15m":
        query = (
            select(
                TelemetryReading.interval_start,
                *(
                    func.sum(getattr(TelemetryReading, c))
                    for c in ("generation_kw", "load_kw", "grid_import_kw", "grid_export_kw")
                ),
            )
            .join(Meter, Meter.id == TelemetryReading.meter_id)
            .where(
                Meter.site_id.in_([s.id for s in selected]),
                TelemetryReading.interval_start >= end - timedelta(seconds=duration),
                TelemetryReading.interval_end <= end,
                TelemetryReading.quality_status == "valid",
            )
            .group_by(TelemetryReading.interval_start)
            .order_by(TelemetryReading.interval_start)
        )
        points = [
            {
                "time": row[0],
                **{
                    k: float(row[i + 1] or 0)
                    for i, k in enumerate(
                        ("generation_kw", "load_kw", "grid_import_kw", "grid_export_kw")
                    )
                },
            }
            for row in db.execute(query)
        ]
    else:
        prepared = []
        for site in selected:
            p = db.get(HouseholdProfile, site.owner_user_id)
            prepared.append(
                (
                    float(ws.capacity(db, site)),
                    p.settings if p else DEFAULTS,
                    str(site.owner_user_id),
                )
            )
        points = []
        for i in range(duration // seconds):
            moment = end - timedelta(seconds=(duration // seconds - 1 - i) * seconds)
            point: dict[str, Any] = {
                "time": moment,
                "generation_kw": 0.0,
                "load_kw": 0.0,
                "grid_import_kw": 0.0,
                "grid_export_kw": 0.0,
            }
            for cap, setup, seed in prepared:
                for key, value in power(moment, cap, setup, seed).items():
                    point[key] = round(point[key] + value, 4)
            points.append(point)
    return {
        "as_of": now(db),
        "resolution": resolution,
        "window": window,
        "points": points,
        "scope": scope,
    }

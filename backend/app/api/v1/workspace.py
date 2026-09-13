"""Authenticated, reviewable workflow endpoints used by the application."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.api.v1.household import HouseholdSetup
from app.core.config import get_settings
from app.db.models import LoginSession, Receipt, User
from app.domain.enums import UserRole
from app.services import workspace_service as service
from app.services.auth_service import COOKIE, authenticate, create_session, require_user, token_hash

router = APIRouter(tags=["connected workspace"])


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=128)


class Registration(Login):
    name: str = Field(min_length=2, max_length=80)
    role: Literal["consumer", "prosumer"] = "consumer"
    capacity_kw: Decimal = Field(default=Decimal(6), ge=1, le=15)
    setup: HouseholdSetup | None = None


class OrderInput(BaseModel):
    side: Literal["buy", "sell"]
    start: datetime
    quantity: Decimal = Field(gt=0, le=10, decimal_places=4)
    price: Decimal = Field(gt=0, le=30, decimal_places=4)

    @field_validator("start")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Delivery time must include a timezone.")
        return value


class Control(BaseModel):
    action: Literal["step", "deliver", "play", "pause", "scenario", "weather", "recover", "live"]
    scenario: Literal["normal", "cloudy", "congestion", "missing"] = "normal"


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=get_settings().app_env == "production",
        samesite="strict",
        max_age=43200,
        path="/",
    )


@router.post("/auth/login")
def login(payload: Login, response: Response, db: DbSession) -> dict[str, str]:
    user = authenticate(db, payload.email, payload.password)
    set_cookie(response, create_session(db, user))
    db.commit()
    return {"name": user.display_name}


@router.post("/auth/register", status_code=201)
def register(payload: Registration, response: Response, db: DbSession) -> dict[str, str]:
    if get_settings().app_env == "production":
        raise HTTPException(403, "Synthetic-community signup is disabled in production.")
    sim = service.state(db, True)
    if len(service.sites(db)) >= 30:
        raise HTTPException(409, "This demo community has reached its 30-site limit.")
    user = service.register(
        db,
        sim,
        payload.email,
        payload.password,
        payload.name,
        payload.role,
        payload.capacity_kw,
        payload.setup.model_dump() if payload.setup else None,
    )
    set_cookie(response, create_session(db, user))
    db.commit()
    return {"name": user.display_name}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: DbSession) -> dict[str, bool]:
    db.execute(
        delete(LoginSession).where(
            LoginSession.token_hash == token_hash(request.cookies.get(COOKIE, ""))
        )
    )
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/workspace")
def workspace(request: Request, db: DbSession) -> JSONResponse:
    return JSONResponse(
        jsonable_encoder(
            service.snapshot(db, require_user(db, request)), custom_encoder={Decimal: str}
        )
    )


@router.post("/workspace/orders", status_code=201)
def place_order(payload: OrderInput, request: Request, db: DbSession) -> dict[str, Any]:
    return service.serialize(
        service.place_order(
            db,
            require_user(db, request),
            payload.start,
            payload.side,
            payload.quantity,
            payload.price,
        )
    )


@router.post("/workspace/orders/{order_id}/cancel")
def cancel(order_id: UUID, request: Request, db: DbSession) -> dict[str, bool]:
    service.cancel_order(db, require_user(db, request), order_id)
    return {"ok": True}


def operator(db: Session, request: Request) -> User:
    user = require_user(db, request)
    if user.role not in (UserRole.OPERATOR, UserRole.ADMIN):
        raise HTTPException(403, "This action requires the community operator.")
    return user


@router.post("/workspace/clear")
def clear(request: Request, db: DbSession) -> dict[str, Any]:
    operator(db, request)
    return {"trades": [service.serialize(t) for t in service.clear_market(db)]}


@router.post("/workspace/control")
def control(payload: Control, request: Request, db: DbSession) -> dict[str, bool]:
    operator(db, request)
    if get_settings().app_env == "production":
        raise HTTPException(403, "Simulation controls are disabled in production.")
    if payload.action in ("step", "deliver"):
        service.state(db, True).live_mode = False
        service.advance(db, deliver=payload.action == "deliver")
    elif payload.action == "live":
        from app.services.experience_service import enable_live

        enable_live(db)
    elif payload.action == "recover":
        service.recover_missing(db)
    elif payload.action == "weather":
        from app.services.workspace_worker import refresh_weather

        refresh_weather(db)
    else:
        sim = service.state(db, True)
        if payload.action == "scenario":
            sim.scenario = payload.scenario
        else:
            sim.live_mode = False
            sim.running = payload.action == "play"
        service.bump(sim)
        db.commit()
    return {"ok": True}


@router.get("/workspace/receipts/{receipt_id}/verify")
def verify(receipt_id: UUID, request: Request, db: DbSession) -> dict[str, Any]:
    user = require_user(db, request)
    allowed = service.snapshot(db, user)["receipts"]
    if not any(r["id"] == receipt_id for r in allowed):
        raise HTTPException(404, "Receipt not found.")
    from app.adapters.ledger.evm import verify_receipt

    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(404, "Receipt not found.")
    return verify_receipt(receipt)

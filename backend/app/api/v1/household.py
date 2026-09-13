"""Profile, live analytics and household-to-household trading API."""

import base64
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.api.deps import DbSession
from app.services import experience_service as experience
from app.services import workspace_service as workspace
from app.services.auth_service import require_user

router = APIRouter(tags=["household experience"])


class HouseholdSetup(BaseModel):
    city: Literal["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"] = "Ahmedabad"
    home_type: Literal["apartment", "independent", "bungalow"] = "independent"
    occupants: int = Field(default=4, ge=1, le=20)
    monthly_kwh: float = Field(default=360, ge=30, le=3000)
    ac_count: int = Field(default=1, ge=0, le=8)
    has_ev: bool = False
    daytime_home: bool = True
    orientation: Literal["south", "east", "west", "north"] = "south"
    tilt: float = Field(default=23, ge=0, le=60)
    retail_rate: float = Field(default=7, ge=0.5, le=30)
    share_stats: bool = True
    avatar: str | None = Field(default=None, max_length=220000)
    photo: str | None = Field(default=None, max_length=320000)

    @field_validator("avatar", "photo")
    @classmethod
    def image_data(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            header, encoded = value.split(",", 1)
            data = base64.b64decode(encoded, validate=True)
            valid = (
                (header == "data:image/jpeg;base64" and data.startswith(b"\xff\xd8\xff"))
                or (header == "data:image/png;base64" and data.startswith(b"\x89PNG\r\n\x1a\n"))
                or (
                    header == "data:image/webp;base64"
                    and data.startswith(b"RIFF")
                    and data[8:12] == b"WEBP"
                )
            )
            if not valid:
                raise ValueError("Unsupported image")
        except (ValueError, TypeError) as exc:
            raise ValueError("Choose a PNG, JPEG or WebP image.") from exc
        return value


class Acceptance(BaseModel):
    quantity: Decimal = Field(gt=0, le=10, decimal_places=4)
    price: Decimal = Field(gt=0, le=30, decimal_places=4)
    request_id: UUID
    own_order_id: UUID | None = None


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def encoded(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        jsonable_encoder(data, custom_encoder={Decimal: str}), status_code=status_code
    )


@router.get("/workspace/dashboard")
def dashboard(request: Request, db: DbSession) -> JSONResponse:
    return encoded(experience.dashboard(db, require_user(db, request)))


@router.get("/workspace/series")
def series(
    request: Request,
    db: DbSession,
    scope: Literal["energy", "community"] = "energy",
    window: Literal["live", "hour", "day"] = "live",
    resolution: Literal["5s", "1m", "15m"] = "5s",
) -> JSONResponse:
    return encoded(experience.series(db, require_user(db, request), scope, window, resolution))


@router.put("/workspace/profile")
def update_profile(payload: HouseholdSetup, request: Request, db: DbSession) -> dict[str, bool]:
    experience.save_profile(db, require_user(db, request), payload.model_dump())
    return {"ok": True}


@router.post("/workspace/orders/{offer_id}/accept", status_code=201)
def accept(offer_id: UUID, payload: Acceptance, request: Request, db: DbSession) -> JSONResponse:
    trade = workspace.accept_offer(
        db,
        require_user(db, request),
        offer_id,
        payload.quantity,
        payload.price,
        payload.request_id,
        payload.own_order_id,
    )
    return encoded(workspace.serialize(trade), status_code=201)


@router.post("/workspace/assistant")
def assistant(payload: ChatInput, request: Request, db: DbSession) -> dict[str, Any]:
    from app.services.energy_assistant import answer

    return answer(db, require_user(db, request), payload.message)

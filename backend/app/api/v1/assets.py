"""Assets / Verification endpoints (docs/05_API_SPEC.md).

Transport only. Paths are written in full rather than under a single prefix
because this resource group spans `/sites`, `/assets` and `/inverters`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.schemas.assets import (
    EnergyAssetCreate,
    EnergyAssetRead,
    InverterCreate,
    InverterRead,
    MeterCreate,
    MeterRead,
    SiteCreate,
    SiteDetail,
    SiteRead,
    VerificationCreate,
    VerificationRead,
)
from app.schemas.common import ErrorResponse
from app.services import asset_service

router = APIRouter(tags=["assets"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"}
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "Conflicting registration"}
}


@router.post(
    "/sites",
    response_model=SiteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a site",
    responses=NOT_FOUND,
)
def create_site(payload: SiteCreate, session: DbSession) -> SiteRead:
    return SiteRead.model_validate(asset_service.create_site(session, payload))


@router.get(
    "/sites/{site_id}",
    response_model=SiteDetail,
    summary="Site details",
    responses=NOT_FOUND,
)
def get_site(site_id: UUID, session: DbSession) -> SiteDetail:
    return SiteDetail.model_validate(asset_service.get_site_detail(session, site_id))


@router.post(
    "/sites/{site_id}/meters",
    response_model=MeterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a meter",
    responses={**NOT_FOUND, **CONFLICT},
)
def attach_meter(site_id: UUID, payload: MeterCreate, session: DbSession) -> MeterRead:
    return MeterRead.model_validate(asset_service.attach_meter(session, site_id, payload))


@router.post(
    "/sites/{site_id}/energy-assets",
    response_model=EnergyAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register PV/battery/other asset",
    responses=NOT_FOUND,
)
def register_energy_asset(
    site_id: UUID, payload: EnergyAssetCreate, session: DbSession
) -> EnergyAssetRead:
    return EnergyAssetRead.model_validate(
        asset_service.register_energy_asset(session, site_id, payload)
    )


@router.post(
    "/assets/{asset_id}/verification",
    response_model=VerificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit verification record",
    responses={**NOT_FOUND, **CONFLICT},
)
def submit_verification(
    asset_id: UUID, payload: VerificationCreate, session: DbSession
) -> VerificationRead:
    return VerificationRead.model_validate(
        asset_service.submit_asset_verification(session, asset_id, payload)
    )


@router.get(
    "/assets/{asset_id}/verification",
    response_model=list[VerificationRead],
    summary="Get verification status",
    responses=NOT_FOUND,
)
def get_verification(asset_id: UUID, session: DbSession) -> list[VerificationRead]:
    records = asset_service.list_asset_verifications(session, asset_id)
    return [VerificationRead.model_validate(record) for record in records]


@router.post(
    "/inverters",
    response_model=InverterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register inverter metadata and adapter type",
    responses={**NOT_FOUND, **CONFLICT},
)
def register_inverter(payload: InverterCreate, session: DbSession) -> InverterRead:
    return InverterRead.model_validate(asset_service.register_inverter(session, payload))

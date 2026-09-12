"""Phase 6 verification: the pricing engine, service and persistence.

Checks the properties the architecture depends on, not that a function returns
a number: components add up, the grid result actually drives the price, an
unknown grid is never priced as a safe one, and the Phase 4 clearing price
survives untouched.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import GridValidationDecision, GridValidationStatus
from app.domain.interfaces.grid import GridMetrics
from app.domain.interfaces.pricing import PricingEngine, PricingRequest
from app.domain.policies.dynamic_pricing import DEFAULT_ENGINE, DEFAULT_PARAMETERS
from app.repositories.pricing import PriceComponentsRepository
from app.services import pricing_service

from .conftest import CLEARING_PRICE, DELIVERY_END, DELIVERY_START, Lifecycle


def _request(**overrides: object) -> PricingRequest:
    base: dict[str, object] = {
        "base_price_inr_per_kwh": CLEARING_PRICE,
        "quantity_kwh": Decimal("10"),
        "delivery_start": DELIVERY_START,
        "delivery_end": DELIVERY_END,
    }
    return PricingRequest(**{**base, **overrides})  # type: ignore[arg-type]


def test_default_engine_satisfies_the_canonical_contract() -> None:
    assert isinstance(DEFAULT_ENGINE, PricingEngine)


def test_components_always_sum_to_the_final_price() -> None:
    """The one property an explainable price may not break."""
    for status, metrics in (
        (GridValidationStatus.SAFE, GridMetrics(max_line_loading_pct=Decimal("40"))),
        (GridValidationStatus.SAFE, GridMetrics(max_line_loading_pct=Decimal("92"))),
        (GridValidationStatus.UNSAFE, GridMetrics(max_line_loading_pct=Decimal("140"))),
        (GridValidationStatus.UNKNOWN, None),
    ):
        result = DEFAULT_ENGINE.quote(
            _request(grid_status=status, grid_metrics=metrics, local_renewable=True)
        )
        assert result.components_sum == result.final_price
        assert len(result.components) == 5


def test_congestion_raises_the_price_as_the_network_loads() -> None:
    """Pricing reacts to the physical constraint, monotonically."""
    prices = [
        DEFAULT_ENGINE.quote(
            _request(
                grid_status=GridValidationStatus.SAFE,
                grid_metrics=GridMetrics(max_line_loading_pct=Decimal(loading)),
            )
        ).final_price
        for loading in ("40", "80", "95", "100")
    ]

    assert prices == sorted(prices)
    assert prices[0] < prices[-1], "a congested feeder must cost more than a quiet one"


@pytest.mark.parametrize("status", [GridValidationStatus.UNKNOWN, GridValidationStatus.UNSAFE])
def test_unknown_and_unsafe_are_never_priced_as_safe(status: GridValidationStatus) -> None:
    """The rule the brief singles out: UNKNOWN is never treated as SAFE."""
    quiet = DEFAULT_ENGINE.quote(
        _request(
            grid_status=GridValidationStatus.SAFE,
            grid_metrics=GridMetrics(max_line_loading_pct=Decimal("10")),
        )
    )
    unclear = DEFAULT_ENGINE.quote(_request(grid_status=status, grid_metrics=None))

    assert unclear.congestion_component > quiet.congestion_component
    assert unclear.recommended_decision is GridValidationDecision.REJECT


def test_missing_metrics_are_not_treated_as_zero_congestion() -> None:
    """A safe verdict with nothing measured cannot buy the cheapest price."""
    result = DEFAULT_ENGINE.quote(
        _request(grid_status=GridValidationStatus.SAFE, grid_metrics=GridMetrics())
    )

    assert result.congestion_component > Decimal("0")


def test_pricing_is_deterministic() -> None:
    """Same inputs, same formula version, same breakdown."""
    request = _request(
        grid_status=GridValidationStatus.SAFE,
        grid_metrics=GridMetrics(max_line_loading_pct=Decimal("85")),
        forecast_confidence=Decimal("0.9"),
    )
    first, second = DEFAULT_ENGINE.quote(request), DEFAULT_ENGINE.quote(request)

    assert first == second
    assert first.formula_version == DEFAULT_PARAMETERS.formula_version


def test_service_persists_a_breakdown_and_leaves_the_clearing_price_alone(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """Phase 6 adjusts the Phase 4 price; it must never overwrite it."""
    row = pricing_service.price_trade(db_session, lifecycle.trade.id)

    assert row.base_market_price == CLEARING_PRICE
    assert (
        row.base_market_price
        + row.time_component
        + row.congestion_component
        + row.imbalance_component
        + row.local_renewable_component
        == row.final_price
    )

    db_session.refresh(lifecycle.trade)
    assert (
        lifecycle.trade.clearing_price_inr_per_kwh == CLEARING_PRICE
    ), "the Phase 4 market clearing price must survive pricing untouched"


def test_service_reaches_the_canonical_engine_not_a_copy(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """A stub engine passed in must actually be the one that prices."""
    recorded: list[PricingRequest] = []

    class RecordingEngine:
        name = "recording"
        formula_version = "test-0"

        def quote(self, request: PricingRequest):  # type: ignore[no-untyped-def]
            recorded.append(request)
            return replace(
                DEFAULT_ENGINE.quote(request),
                engine=self.name,
                formula_version=self.formula_version,
            )

    row = pricing_service.price_trade(db_session, lifecycle.trade.id, engine=RecordingEngine())

    assert len(recorded) == 1
    assert recorded[0].base_price_inr_per_kwh == CLEARING_PRICE
    assert row.formula_version == "test-0"


def test_breakdown_history_is_kept_and_the_latest_wins(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    first = pricing_service.price_trade(db_session, lifecycle.trade.id)
    second = pricing_service.price_trade(db_session, lifecycle.trade.id)

    assert first.id != second.id
    assert len(PriceComponentsRepository(db_session).list_for_trade(lifecycle.trade.id)) == 2
    assert pricing_service.get_breakdown(db_session, lifecycle.trade.id).id == second.id


def test_pricing_reads_the_grid_verdict_from_the_stored_validation(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """A trade never validated is priced as UNKNOWN, not as safe."""
    result = pricing_service.quote_trade(db_session, lifecycle.trade.id)

    assert result.grid_status is GridValidationStatus.UNKNOWN
    assert result.recommended_decision is GridValidationDecision.REJECT

"""Phase 5 amendments: electrical capacity, tri-state outcome, and the trade link.

Three decisions the project lead locked after reviewing the Phase 5 handoff:

* the twin records the ratings that make loading computable at all;
* a validation concludes ``safe``, ``unsafe`` **or** ``unknown``, and a failure
  or a gap in the data is never the first of those;
* ``trades.grid_validation_id`` points at a real validation run.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import GridNode, MarketSession, Order, Site, Trade, User
from app.db.models.grid import GridValidationRun
from app.domain.enums import (
    GridNodeType,
    GridValidationDecision,
    GridValidationStatus,
    GridViolationType,
    MarketSessionStatus,
    MarketType,
    OrderSide,
    UserRole,
    UserStatus,
)
from app.domain.interfaces.grid import (
    GridMetrics,
    GridValidationRequest,
    NetworkLine,
    NetworkModel,
    NetworkNode,
    NetworkTransformer,
)
from app.domain.policies.grid_limits import (
    DEFAULT_LIMITS,
    decide,
    describe_missing_ratings,
    effective_status,
    evaluate_metrics,
    resolve_status,
)
from app.services import grid_validation_service as service

from .conftest import (
    DELIVERY_END,
    DELIVERY_START,
    FEEDER,
    SERVICE_LINE_RATING_KW,
    TRANSFORMER_RATING_KW,
    FailingGridEngine,
    StubGridEngine,
    violation,
)

# ---------------------------------------------------------------------------
# 1. The tri-state outcome
# ---------------------------------------------------------------------------


def test_status_has_exactly_three_states() -> None:
    """Two is not enough: "we could not tell" is a real outcome."""
    assert {s.value for s in GridValidationStatus} == {"safe", "unsafe", "unknown"}


def test_only_a_positively_safe_network_permits_a_trade() -> None:
    assert GridValidationStatus.SAFE.permits_trade is True
    assert GridValidationStatus.UNSAFE.permits_trade is False
    assert GridValidationStatus.UNKNOWN.permits_trade is False


def test_unknown_is_the_only_state_that_was_never_evaluated() -> None:
    """Which is exactly the distinction a boolean throws away."""
    assert GridValidationStatus.SAFE.was_evaluated is True
    assert GridValidationStatus.UNSAFE.was_evaluated is True
    assert GridValidationStatus.UNKNOWN.was_evaluated is False


def test_an_unknown_network_is_rejected_like_an_unsafe_one() -> None:
    assert (
        decide(status=GridValidationStatus.UNKNOWN, caused_violations=())
        is GridValidationDecision.REJECT
    )


def test_missing_ratings_downgrade_a_safe_verdict_to_unknown() -> None:
    """The voltages were checked; the overloads were not."""
    downgraded = resolve_status(GridValidationStatus.SAFE, unrated_elements=(uuid.uuid4(),))

    assert downgraded is GridValidationStatus.UNKNOWN


def test_missing_ratings_never_change_an_unsafe_verdict() -> None:
    """A real breach was found; incomplete data does not soften it."""
    assert (
        resolve_status(GridValidationStatus.UNSAFE, unrated_elements=(uuid.uuid4(),))
        is GridValidationStatus.UNSAFE
    )


def test_complete_ratings_leave_every_verdict_alone() -> None:
    for status in GridValidationStatus:
        assert resolve_status(status, unrated_elements=()) is status


def test_a_caused_violation_makes_the_run_unsafe_whatever_the_engine_said() -> None:
    """Safe without the trade is not the question the record answers."""
    caused = evaluate_metrics(GridMetrics(max_line_loading_pct=Decimal("130")), DEFAULT_LIMITS)

    assert (
        effective_status(GridValidationStatus.SAFE, caused_violations=caused)
        is GridValidationStatus.UNSAFE
    )


def test_unknown_survives_a_trade_that_caused_nothing_visible() -> None:
    """A network nobody could assess does not become assessable by luck."""
    assert (
        effective_status(GridValidationStatus.UNKNOWN, caused_violations=())
        is GridValidationStatus.UNKNOWN
    )


def test_result_reports_safe_only_for_the_safe_state() -> None:
    """The derived boolean is conservative; the status keeps the detail."""
    engine = StubGridEngine(status=GridValidationStatus.UNKNOWN)
    result = engine.validate(
        GridValidationRequest(
            network=NetworkModel(version="t", nodes=()),
            limits=DEFAULT_LIMITS,
            interval_start=DELIVERY_START,
            interval_end=DELIVERY_END,
        )
    )

    assert result.status is GridValidationStatus.UNKNOWN
    assert result.safe is False


# ---------------------------------------------------------------------------
# 2. Missing information is never safe, end to end
# ---------------------------------------------------------------------------


def test_an_unrated_feeder_can_never_be_validated_as_safe(
    db_session: Session, make_feeder: object
) -> None:
    """The twin as it was before capacity was recorded.

    The engine sees no violation and says the network is safe. It is not
    entitled to: no rating means no loading percentage, so nothing about the
    thermal state of this feeder was ever checked.
    """
    nodes = make_feeder(FEEDER, rated=False)  # type: ignore[operator]
    engine = StubGridEngine()

    run = service.validate_trade(
        db_session,
        engine=engine,
        trade_id=uuid.uuid4(),
        seller_node_id=nodes[2].id,
        buyer_node_id=nodes[3].id,
        quantity_kwh=Decimal("10"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )

    assert run.status is GridValidationStatus.UNKNOWN
    assert run.decision is GridValidationDecision.REJECT
    assert run.reason is not None
    assert "not assessable" in run.reason


def test_a_rated_feeder_validates_normally(db_session: Session, make_feeder: object) -> None:
    """The same scenario, once the ratings exist."""
    nodes = make_feeder(FEEDER)  # type: ignore[operator]

    run = service.validate_trade(
        db_session,
        engine=StubGridEngine(),
        trade_id=uuid.uuid4(),
        seller_node_id=nodes[2].id,
        buyer_node_id=nodes[3].id,
        quantity_kwh=Decimal("10"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )

    assert run.status is GridValidationStatus.SAFE
    assert run.decision is GridValidationDecision.ACCEPT


def test_a_partially_rated_feeder_is_still_unknown(
    db_session: Session, make_feeder: object
) -> None:
    """One unrated conductor is enough: that element cannot be assessed."""
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    nodes[3].rated_capacity_kw = None
    db_session.flush()

    run = service.validate_trade(
        db_session,
        engine=StubGridEngine(),
        trade_id=uuid.uuid4(),
        seller_node_id=nodes[2].id,
        buyer_node_id=nodes[3].id,
        quantity_kwh=Decimal("10"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )

    assert run.status is GridValidationStatus.UNKNOWN
    assert run.reason == describe_missing_ratings((nodes[3].id,))


def test_an_unrated_feeder_still_reports_a_real_violation(
    db_session: Session, make_feeder: object
) -> None:
    """Unknown ratings must not mask a breach the engine did find."""
    nodes = make_feeder(FEEDER, rated=False)  # type: ignore[operator]
    engine = StubGridEngine(
        metrics=GridMetrics(min_voltage_pu=Decimal("0.88")),
        violations=(violation(GridViolationType.UNDER_VOLTAGE, "0.88", "0.94"),),
        status=GridValidationStatus.UNSAFE,
    )

    run = service.validate_trade(
        db_session,
        engine=engine,
        trade_id=uuid.uuid4(),
        seller_node_id=nodes[2].id,
        buyer_node_id=nodes[3].id,
        quantity_kwh=Decimal("10"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )

    assert run.status is GridValidationStatus.UNSAFE
    assert run.reason is not None
    assert "under_voltage" in run.reason


# ---------------------------------------------------------------------------
# 3. The capacity model
# ---------------------------------------------------------------------------


def test_build_network_carries_the_ratings_recorded_in_the_twin(
    db_session: Session, make_feeder: object
) -> None:
    """Each edge gets the rating of the element it represents."""
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    network = service.build_network(db_session, feeder_id=FEEDER)

    transformer = network.transformers[0]
    assert transformer.transformer_id == nodes[1].id
    assert transformer.rating_kw == TRANSFORMER_RATING_KW

    assert {line.rating_kw for line in network.lines} == {SERVICE_LINE_RATING_KW}
    assert network.has_complete_ratings is True
    assert network.unrated_elements == ()


def test_build_network_reports_an_unrated_element_rather_than_inventing_one(
    db_session: Session, make_feeder: object
) -> None:
    """A made-up denominator would turn a guess into a percentage."""
    nodes = make_feeder(FEEDER, rated=False)  # type: ignore[operator]
    network = service.build_network(db_session, feeder_id=FEEDER)

    assert all(line.rating_kw is None for line in network.lines)
    assert network.transformers[0].rating_kw is None
    assert network.has_complete_ratings is False
    assert set(network.unrated_elements) == {n.id for n in nodes[1:]}


def test_loading_percentages_are_computable_from_the_model(
    db_session: Session, make_feeder: object
) -> None:
    """The point of the capacity extension, stated as arithmetic.

    An engine is what actually computes these; this asserts the model carries
    everything it needs to, which it previously did not.
    """
    make_feeder(FEEDER)  # type: ignore[operator]
    network = service.build_network(db_session, feeder_id=FEEDER)

    transformer = network.transformers[0]
    line = network.lines[0]
    assert transformer.rating_kw is not None
    assert line.rating_kw is not None

    # 200 kW through a 250 kW transformer; 45 kW through a 60 kW conductor.
    transformer_loading_percent = Decimal("200") / transformer.rating_kw * Decimal("100")
    line_loading_percent = Decimal("45") / line.rating_kw * Decimal("100")

    assert transformer_loading_percent == Decimal("80")
    assert line_loading_percent == Decimal("75")


def test_a_network_with_no_edges_is_trivially_complete() -> None:
    """Nothing whose loading could be unknown."""
    node = NetworkNode(
        node_id=uuid.uuid4(),
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11"),
    )
    network = NetworkModel(version="t", nodes=(node,))

    assert network.has_complete_ratings is True


def test_unrated_elements_names_both_lines_and_transformers() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    network = NetworkModel(
        version="t",
        nodes=(),
        lines=(
            NetworkLine(line_id=a, from_node_id=c, to_node_id=a, rating_kw=Decimal("50")),
            NetworkLine(line_id=b, from_node_id=c, to_node_id=b),
        ),
        transformers=(NetworkTransformer(transformer_id=c, from_node_id=a, to_node_id=c),),
    )

    assert set(network.unrated_elements) == {b, c}


def test_database_refuses_a_zero_or_negative_rating(db_session: Session) -> None:
    """Zero is not "unknown" — it would compute as infinite loading."""
    db_session.add(
        GridNode(
            external_ref=f"sub-{uuid.uuid4().hex[:8]}",
            node_type=GridNodeType.SUBSTATION,
            nominal_voltage_kv=Decimal("11.0000"),
            rated_capacity_kw=Decimal("0"),
        )
    )
    with pytest.raises(IntegrityError, match="rated_capacity_positive"):
        db_session.flush()


def test_a_rating_is_optional(db_session: Session) -> None:
    """The twin is allowed not to know, and says so with NULL."""
    node = GridNode(
        external_ref=f"sub-{uuid.uuid4().hex[:8]}",
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11.0000"),
    )
    db_session.add(node)
    db_session.flush()

    assert node.rated_capacity_kw is None


# ---------------------------------------------------------------------------
# 4. trades.grid_validation_id
# ---------------------------------------------------------------------------


def _make_trade(session: Session) -> Trade:
    """The minimum market rows needed to hang a trade off.

    Built directly rather than through the Phase 4 service: this is a test
    about a foreign key, and it must not depend on market orchestration.
    """
    user = User(
        display_name="Grid FK Owner",
        role=UserRole.PROSUMER,
        status=UserStatus.ACTIVE,
        email=f"gridfk-{uuid.uuid4().hex[:8]}@example.org",
    )
    session.add(user)
    session.flush()

    site = Site(owner_user_id=user.id, name="Grid FK Site")
    market_session = MarketSession(
        market_date=date(2026, 6, 2),
        market_type=MarketType.DAY_AHEAD,
        status=MarketSessionStatus.OPEN,
    )
    session.add_all([site, market_session])
    session.flush()

    common = {
        "market_session_id": market_session.id,
        "user_id": user.id,
        "site_id": site.id,
        "delivery_start": DELIVERY_START,
        "delivery_end": DELIVERY_END,
        "energy_kwh": Decimal("10"),
    }
    buy = Order(side=OrderSide.BUY, max_price_inr_per_kwh=Decimal("9"), **common)
    sell = Order(side=OrderSide.SELL, min_price_inr_per_kwh=Decimal("5"), **common)
    session.add_all([buy, sell])
    session.flush()

    trade = Trade(
        buy_order_id=buy.id,
        sell_order_id=sell.id,
        quantity_kwh=Decimal("10"),
        clearing_price_inr_per_kwh=Decimal("7"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
    )
    session.add(trade)
    session.flush()
    return trade


def test_a_trade_can_cite_the_validation_that_judged_it(
    db_session: Session, simple_network: NetworkModel
) -> None:
    trade = _make_trade(db_session)
    run = service.validate_scenario(
        db_session,
        engine=StubGridEngine(),
        network=simple_network,
        proposed_injections=(),
        interval_start=DELIVERY_START,
        interval_end=DELIVERY_END,
        trade_id=trade.id,
    )

    trade.grid_validation_id = run.id
    db_session.flush()
    db_session.refresh(trade)

    assert trade.grid_validation_id == run.id


def test_a_trade_cannot_cite_a_validation_that_never_happened(db_session: Session) -> None:
    """The whole point of the foreign key."""
    trade = _make_trade(db_session)
    trade.grid_validation_id = uuid.uuid4()

    with pytest.raises(IntegrityError, match="fk_trades_grid_validation_id_grid_validation_runs"):
        db_session.flush()


def test_a_cited_validation_cannot_be_deleted(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """RESTRICT: the evidence outlives nothing that still points at it."""
    trade = _make_trade(db_session)
    run = service.validate_scenario(
        db_session,
        engine=StubGridEngine(),
        network=simple_network,
        proposed_injections=(),
        interval_start=DELIVERY_START,
        interval_end=DELIVERY_END,
        trade_id=trade.id,
    )
    trade.grid_validation_id = run.id
    db_session.flush()

    with pytest.raises(IntegrityError, match="fk_trades_grid_validation_id_grid_validation_runs"):
        db_session.execute(
            text("DELETE FROM grid_validation_runs WHERE id = :id"), {"id": str(run.id)}
        )


def test_an_unvalidated_trade_is_distinguishable_from_a_validated_one(
    db_session: Session,
) -> None:
    """NULL means nobody has asked the grid about this trade yet."""
    trade = _make_trade(db_session)

    assert trade.grid_validation_id is None


def test_a_failed_validation_is_still_citable(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """An `unknown` run is a record like any other; the trade may cite it.

    What it must not do is let the trade proceed, and the decision on the run
    is what says so.
    """
    trade = _make_trade(db_session)
    with pytest.raises(service.GridEngineError) as caught:
        service.validate_scenario(
            db_session,
            engine=FailingGridEngine(),
            network=simple_network,
            proposed_injections=(),
            interval_start=DELIVERY_START,
            interval_end=DELIVERY_END,
            trade_id=trade.id,
        )

    run_id = uuid.UUID(caught.value.details["grid_validation_run_id"])
    trade.grid_validation_id = run_id
    db_session.flush()

    run = db_session.get(GridValidationRun, run_id)
    assert run is not None
    assert run.status is GridValidationStatus.UNKNOWN
    assert run.decision is GridValidationDecision.REJECT

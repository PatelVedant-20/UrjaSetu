"""The dynamic pricing formula.

docs/01_FINAL_ARCHITECTURE.md specifies the `pricing` module as
"Base price + time + congestion + imbalance/risk + local-renewable component",
and docs/04_DATA_MODEL.md entity 18 fixes those five names as stored columns.
This module is that formula:

    final = base
          + time            (signed: peak adds, solar hours subtract)
          + congestion      (>= 0, driven by the Phase 5 grid result)
          + imbalance       (>= 0, driven by Phase 3 forecast confidence)
          + local_renewable (<= 0, an incentive)

Each component is a fraction *of the base price* rather than an absolute
amount, so the formula behaves the same on a 3 INR/kWh feeder and an
8 INR/kWh one, and so no component carries a currency assumption of its own.

Pure and deterministic: plain values in, plain values out, no I/O and no clock.
The delivery window comes from the request; nothing here reads `now`.

--------------------------------------------------------------------------
COEFFICIENTS ARE PROVISIONAL
--------------------------------------------------------------------------
No project document specifies a threshold, a coefficient or a tariff band.
docs/01_FINAL_ARCHITECTURE.md names the five components, docs/04_DATA_MODEL.md
names the five columns, and docs/11_REGULATORY_AND_INDIA_CONTEXT.md records
that CEA's AMI requirements include TOD/TOU metering — which is the documented
basis for a time-varying component existing at all, and the end of what the
documentation settles.

Every number below is therefore declared in one place, as a parameter, with the
reasoning for its default written beside it. They are **placeholders pending a
ruling**, not derived values, and none of them is referenced anywhere else in
the codebase: replacing `DEFAULT_PARAMETERS` changes the entire pricing
behaviour, and bumping `formula_version` keeps every price already stored
explainable under the formula that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.enums import (
    GridValidationDecision,
    GridValidationStatus,
    PriceComponentKind,
    TimeOfDayBand,
)
from app.domain.interfaces.grid import GridMetrics
from app.domain.interfaces.pricing import (
    PriceComponent,
    PricingRequest,
    PricingResult,
)
from app.domain.policies.clearing_price import quantize_price

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

# Indian Standard Time. A tariff band is a local-clock concept: "evening peak"
# means evening where the feeder is. Timestamps stay UTC everywhere
# (docs/00_PROJECT_BIBLE.md section 6); this offset is applied only to decide
# which band a delivery window falls in, and is stated as a parameter rather
# than hidden inside a conversion.
IST = timedelta(hours=5, minutes=30)


@dataclass(frozen=True, slots=True)
class TariffBand:
    """A local-clock window and what it does to the price.

    Hours are half-open, `[start_hour, end_hour)`, in the parameter set's local
    time. A window that wraps midnight is rejected rather than silently
    mishandled — express it as two bands.
    """

    band: TimeOfDayBand
    start_hour: int
    end_hour: int
    # Signed fraction of the base price. Positive is a surcharge.
    fraction: Decimal

    def __post_init__(self) -> None:
        if not 0 <= self.start_hour < 24 or not 0 < self.end_hour <= 24:
            raise ValueError(f"{self.band} hours must lie within a day")
        if self.start_hour >= self.end_hour:
            raise ValueError(
                f"{self.band} window {self.start_hour}-{self.end_hour} wraps midnight; "
                "express it as two bands"
            )

    def contains(self, hour: int) -> bool:
        return self.start_hour <= hour < self.end_hour


@dataclass(frozen=True, slots=True)
class PricingParameters:
    """Every number the formula uses, in one replaceable object.

    Kept together so that "what would change the price?" has a single answer,
    and so a future tariff schedule arrives as data rather than as edits spread
    through the arithmetic.
    """

    # Bumped whenever any value here changes, because a stored price must stay
    # attributable to the formula that produced it.
    formula_version: str = "1.0.0"
    engine_name: str = "component_pricing"

    # ---- time ------------------------------------------------------------
    #
    # PROVISIONAL. Aligned to the shape of Indian ToD tariffs — an evening
    # peak, and a daytime window when rooftop PV is abundant — but the hours
    # and the percentages are placeholders. The DISCOM/GERC ToD schedule must
    # replace them, and no project document supplies it.
    local_utc_offset: timedelta = IST
    tariff_bands: tuple[TariffBand, ...] = (
        TariffBand(TimeOfDayBand.PEAK, 18, 22, Decimal("0.10")),
        TariffBand(TimeOfDayBand.SOLAR, 9, 16, Decimal("-0.05")),
    )

    # ---- congestion ------------------------------------------------------
    #
    # PROVISIONAL. Below the threshold the network has headroom and congestion
    # costs nothing; between the threshold and the rating the charge ramps
    # linearly; at or above the rating it is capped. 70 % is a planning
    # convention, not a documented figure. The cap bounds the component so the
    # sum of the parts needs no clamping afterwards.
    congestion_threshold_pct: Decimal = Decimal("70")
    congestion_max_fraction: Decimal = Decimal("0.25")

    # ---- imbalance / risk ------------------------------------------------
    #
    # PROVISIONAL. Uncertainty is `1 - confidence`, and this is what a full
    # unit of it costs: a forecast at 0.85 confidence adds 1.5 %.
    imbalance_fraction_per_uncertainty: Decimal = Decimal("0.10")
    # What an *absent* confidence costs. Not zero: a provider that reports no
    # uncertainty has not reported certainty, and pricing it as free would make
    # the naive baseline the cheapest thing to sell against.
    unknown_confidence_fraction: Decimal = Decimal("0.05")

    # ---- local renewable -------------------------------------------------
    #
    # PROVISIONAL. The incentive for energy that is both renewable and stays on
    # the local feeder. What *qualifies* is decided in the pricing service, not
    # here; this is only what qualifying is worth.
    local_renewable_fraction: Decimal = Decimal("0.05")

    # ---- decision --------------------------------------------------------
    #
    # How large the congestion component must be, relative to the base price,
    # before the recommendation is REPRICE rather than ACCEPT. Below this the
    # surcharge is noise; see `recommend` for why only congestion counts.
    reprice_threshold_fraction: Decimal = Decimal("0.02")

    def __post_init__(self) -> None:
        for name in (
            "congestion_max_fraction",
            "imbalance_fraction_per_uncertainty",
            "unknown_confidence_fraction",
            "local_renewable_fraction",
            "reprice_threshold_fraction",
        ):
            if getattr(self, name) < ZERO:
                raise ValueError(f"{name} must not be negative")
        if not ZERO < self.congestion_threshold_pct < HUNDRED:
            raise ValueError("congestion_threshold_pct must lie strictly between 0 and 100")

        # The price may never reach zero or turn negative. Only two components
        # can subtract, so bounding their sum below 1 guarantees it for every
        # possible input, and removes any need to clamp the total afterwards.
        deepest_discount = self.local_renewable_fraction + max(
            (-band.fraction for band in self.tariff_bands if band.fraction < ZERO),
            default=ZERO,
        )
        if deepest_discount >= ONE:
            raise ValueError(
                "the discounting components could drive the price to zero: "
                f"{deepest_discount} of the base price"
            )

        seen = [band.band for band in self.tariff_bands]
        if len(seen) != len(set(seen)):
            raise ValueError("each tariff band may be declared at most once")


DEFAULT_PARAMETERS = PricingParameters()


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def band_for(moment: datetime, parameters: PricingParameters) -> TimeOfDayBand:
    """Which tariff band a delivery window starts in.

    The window's *start* decides, not its midpoint or its end: a day-ahead
    market names the interval by when delivery begins, and splitting a price
    across bands would produce two prices for one trade.
    """
    local_hour = (moment + parameters.local_utc_offset).hour
    for band in parameters.tariff_bands:
        if band.contains(local_hour):
            return band.band
    return TimeOfDayBand.NORMAL


def time_component(request: PricingRequest, parameters: PricingParameters) -> PriceComponent:
    """What the delivery window itself is worth."""
    band = band_for(request.delivery_start, parameters)
    fraction = next(
        (b.fraction for b in parameters.tariff_bands if b.band is band),
        ZERO,
    )
    local_hour = (request.delivery_start + parameters.local_utc_offset).hour

    if fraction == ZERO:
        reason = f"delivery at {local_hour:02d}:00 local falls outside any tariff band"
    elif fraction > ZERO:
        reason = f"{band.value} band at {local_hour:02d}:00 local adds {_as_pct(fraction)}"
    else:
        reason = (
            f"{band.value} band at {local_hour:02d}:00 local returns {_as_pct(-fraction)} "
            "for consuming while local generation is abundant"
        )

    return PriceComponent(
        kind=PriceComponentKind.TIME,
        amount_inr_per_kwh=quantize_price(request.base_price_inr_per_kwh * fraction),
        reason=reason,
    )


def utilisation_pct(metrics: GridMetrics | None) -> Decimal | None:
    """How loaded the worst element of the network is, as a percentage.

    The larger of line and transformer loading, because congestion is set by
    whichever element runs out of capacity first. `None` when the engine
    computed neither — which is not the same as zero, and is never priced as
    though it were.
    """
    if metrics is None:
        return None
    observed = [
        value
        for value in (metrics.max_line_loading_pct, metrics.max_transformer_loading_pct)
        if value is not None
    ]
    return max(observed) if observed else None


def congestion_fraction(
    *,
    status: GridValidationStatus,
    metrics: GridMetrics | None,
    parameters: PricingParameters,
) -> tuple[Decimal, str]:
    """The congestion surcharge as a fraction of the base price, and why.

    Driven by the Phase 5 result and by nothing else: no market quantity, no
    order count, no proxy for scarcity. Congestion is a physical fact about the
    network, and inferring it from market numbers would let a busy market look
    like a constrained feeder.
    """
    if status is GridValidationStatus.UNSAFE:
        return (
            parameters.congestion_max_fraction,
            "grid validation found the network unsafe for this trade; "
            f"the maximum congestion component of {_as_pct(parameters.congestion_max_fraction)} "
            "applies",
        )

    if status is GridValidationStatus.UNKNOWN:
        # The conservative end of the range, because no cheaper figure can be
        # justified from evidence that does not exist. The recommendation is
        # REJECT regardless, so this number explains rather than charges.
        return (
            parameters.congestion_max_fraction,
            "the grid state for this trade is unknown — never assumed safe — so the "
            f"maximum congestion component of {_as_pct(parameters.congestion_max_fraction)} "
            "applies",
        )

    loading = utilisation_pct(metrics)
    if loading is None:
        return (
            parameters.congestion_max_fraction,
            "the network was judged safe but reported no loading measurement, so "
            "congestion cannot be assessed and is priced at its maximum",
        )

    if loading <= parameters.congestion_threshold_pct:
        return (
            ZERO,
            f"worst element at {_trim(loading)}% of rating, within the "
            f"{_trim(parameters.congestion_threshold_pct)}% headroom threshold",
        )

    span = HUNDRED - parameters.congestion_threshold_pct
    over = min(loading, HUNDRED) - parameters.congestion_threshold_pct
    fraction = parameters.congestion_max_fraction * (over / span)
    return (
        fraction,
        f"worst element at {_trim(loading)}% of rating, "
        f"{_trim(loading - parameters.congestion_threshold_pct)} points above the "
        f"{_trim(parameters.congestion_threshold_pct)}% threshold",
    )


def congestion_component(request: PricingRequest, parameters: PricingParameters) -> PriceComponent:
    fraction, reason = congestion_fraction(
        status=request.grid_status, metrics=request.grid_metrics, parameters=parameters
    )
    return PriceComponent(
        kind=PriceComponentKind.CONGESTION,
        amount_inr_per_kwh=quantize_price(request.base_price_inr_per_kwh * fraction),
        reason=reason,
    )


def imbalance_component(request: PricingRequest, parameters: PricingParameters) -> PriceComponent:
    """What the risk of not delivering as forecast is worth.

    Consumes the confidence the Phase 3 provider already reported. It does not
    forecast anything, and it contains no model.
    """
    confidence = request.forecast_confidence
    if confidence is None:
        fraction = parameters.unknown_confidence_fraction
        reason = (
            "the forecast this trade rests on reported no confidence, which is not "
            f"certainty; {_as_pct(fraction)} applies"
        )
    else:
        bounded = min(max(confidence, ZERO), ONE)
        uncertainty = ONE - bounded
        fraction = uncertainty * parameters.imbalance_fraction_per_uncertainty
        reason = (
            f"forecast confidence {_trim(bounded)} leaves {_as_pct(uncertainty)} "
            "uncertainty to cover"
        )

    return PriceComponent(
        kind=PriceComponentKind.IMBALANCE,
        amount_inr_per_kwh=quantize_price(request.base_price_inr_per_kwh * fraction),
        reason=reason,
    )


def local_renewable_component(
    request: PricingRequest, parameters: PricingParameters
) -> PriceComponent:
    """The incentive for renewable energy that stays on the local feeder.

    Never a blanket discount. `local_renewable` is established from the twin
    and the asset registry by the pricing service, and a trade that does not
    qualify receives nothing — recorded explicitly as zero, so the breakdown
    still says why.
    """
    if not request.local_renewable:
        return PriceComponent(
            kind=PriceComponentKind.LOCAL_RENEWABLE,
            amount_inr_per_kwh=quantize_price(ZERO),
            reason="the trade is not both locally delivered and renewable, so no incentive applies",
        )

    amount = quantize_price(request.base_price_inr_per_kwh * parameters.local_renewable_fraction)
    return PriceComponent(
        kind=PriceComponentKind.LOCAL_RENEWABLE,
        amount_inr_per_kwh=-amount,
        reason=(
            f"renewable energy delivered on the same feeder returns "
            f"{_as_pct(parameters.local_renewable_fraction)}"
        ),
    )


def recommend(
    *,
    status: GridValidationStatus,
    base_price: Decimal,
    congestion: Decimal,
    parameters: PricingParameters,
) -> GridValidationDecision:
    """What pricing suggests should happen to this trade.

    A recommendation, never an action: Phase 6 does not approve, commit or
    modify a trade, and does not overrule Phase 5.

    `REPRICE` is judged on the **congestion component alone**, not on how far
    the final price sits from the base. docs/00_PROJECT_BIBLE.md section 4
    places this decision immediately after grid validation, so it answers "did
    the network change what this trade should cost?". The time and
    local-renewable terms are the standing tariff — they apply on a completely
    unloaded feeder — and letting a scheduled off-peak discount report as a
    reprice would make almost every trade look like a grid intervention.

    `REDUCE` and `SHIFT` are reachable in the vocabulary and deliberately not
    emitted here. Both mean "this trade would be safe if it were different",
    which can only be established by re-running the grid solver against a
    counterfactual quantity or window — orchestration this phase does not
    perform.
    """
    if not status.permits_trade:
        return GridValidationDecision.REJECT
    if base_price <= ZERO or congestion <= ZERO:
        return GridValidationDecision.ACCEPT
    if congestion / base_price > parameters.reprice_threshold_fraction:
        return GridValidationDecision.REPRICE
    return GridValidationDecision.ACCEPT


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComponentPricingEngine:
    """The default `PricingEngine`: base price plus five documented components.

    Satisfies the Protocol structurally — no inheritance — so a different
    formula is a different class and nothing else has to change. Holds its
    parameters rather than reading them from anywhere, which is what makes two
    engines with different coefficients able to coexist in one process.
    """

    parameters: PricingParameters = field(default_factory=lambda: DEFAULT_PARAMETERS)

    @property
    def name(self) -> str:
        return self.parameters.engine_name

    @property
    def formula_version(self) -> str:
        return self.parameters.formula_version

    def with_parameters(self, parameters: PricingParameters) -> ComponentPricingEngine:
        return replace(self, parameters=parameters)

    def quote(self, request: PricingRequest) -> PricingResult:
        if request.base_price_inr_per_kwh < ZERO:
            raise ValueError("base price must not be negative")

        base = quantize_price(request.base_price_inr_per_kwh)
        time_part = time_component(request, self.parameters)
        congestion_part = congestion_component(request, self.parameters)
        imbalance_part = imbalance_component(request, self.parameters)
        renewable_part = local_renewable_component(request, self.parameters)

        # Summed from the quantised parts, so the stored breakdown adds up
        # exactly. Nothing is clamped afterwards: each component is bounded
        # where it is computed, and `PricingParameters` guarantees the
        # discounts can never reach the base price.
        final = (
            base
            + time_part.amount_inr_per_kwh
            + congestion_part.amount_inr_per_kwh
            + imbalance_part.amount_inr_per_kwh
            + renewable_part.amount_inr_per_kwh
        )

        base_part = PriceComponent(
            kind=PriceComponentKind.BASE,
            amount_inr_per_kwh=base,
            reason="Phase 4 market clearing price for this pairing",
        )

        return PricingResult(
            formula_version=self.formula_version,
            engine=self.name,
            base_market_price=base,
            time_component=time_part.amount_inr_per_kwh,
            congestion_component=congestion_part.amount_inr_per_kwh,
            imbalance_component=imbalance_part.amount_inr_per_kwh,
            local_renewable_component=renewable_part.amount_inr_per_kwh,
            final_price=final,
            components=(base_part, time_part, congestion_part, imbalance_part, renewable_part),
            recommended_decision=recommend(
                status=request.grid_status,
                base_price=base,
                congestion=congestion_part.amount_inr_per_kwh,
                parameters=self.parameters,
            ),
            grid_status=request.grid_status,
        )


DEFAULT_ENGINE = ComponentPricingEngine()


# ---------------------------------------------------------------------------
# Formatting helpers for the reason strings
# ---------------------------------------------------------------------------


def _as_pct(fraction: Decimal) -> str:
    return f"{_trim(fraction * HUNDRED)}%"


def _trim(value: Decimal) -> str:
    """Render a Decimal without trailing zeros, and without going through float."""
    normalised = value.normalize()
    text = format(normalised, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text

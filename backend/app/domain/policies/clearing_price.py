"""Market clearing price.

The price at which a matched buy and sell settle, given the two limit prices
they brought to the market.

Deliberately **outside** the matching engine. An engine decides *who* trades
with *whom* and *how much*; what that energy costs is a separate business rule,
and keeping it separate means the rule can be reviewed and changed without
touching the algorithm — and that replacing the engine cannot quietly change
pricing.

Phase 4 scope only. docs/04_DATA_MODEL.md entity 18 (`price_components`) adds
time-of-day, congestion, imbalance and local-renewable components in Phase 5;
this module deliberately contains none of them, and none of those words appear
here. What it produces is the *base* market clearing price those components
will later build on.

Pure and deterministic: plain values in, plain value out, no I/O and no clock.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# INR/kWh, stored to four decimal places (docs/00_PROJECT_BIBLE.md section 6:
# price in INR/kWh, with paise-level precision where needed).
PRICE_QUANTUM = Decimal("0.0001")


class PriceCrossError(ValueError):
    """The two orders do not overlap in price, so there is no trade to price.

    A buyer's ceiling below a seller's floor is not a cheap trade — it is no
    trade. Returning a number anyway would invent a price neither party agreed
    to.
    """


def midpoint_clearing_price(
    *, buy_max_inr_per_kwh: Decimal, sell_min_inr_per_kwh: Decimal
) -> Decimal:
    """Split the surplus between the two parties.

    When a buyer will pay at most B and a seller will accept at least S with
    S <= B, any price in [S, B] clears. The midpoint is the neutral choice: it
    divides the bargaining range equally, so neither side is systematically
    advantaged by the platform's own rule.

    Raises `PriceCrossError` when S > B, because there is nothing to price.
    """
    if sell_min_inr_per_kwh > buy_max_inr_per_kwh:
        raise PriceCrossError(
            f"Seller floor {sell_min_inr_per_kwh} exceeds buyer ceiling "
            f"{buy_max_inr_per_kwh}; the orders do not cross."
        )

    midpoint = (buy_max_inr_per_kwh + sell_min_inr_per_kwh) / Decimal(2)
    return quantize_price(midpoint)


def prices_cross(
    *, buy_max_inr_per_kwh: Decimal | None, sell_min_inr_per_kwh: Decimal | None
) -> bool:
    """Whether a buy and a sell overlap in price at all.

    An order missing its side's bound cannot cross: docs/04_DATA_MODEL.md
    requires a buy to carry a max price and a sell a min price, and treating a
    missing bound as "any price" would let an unpriced order trade at whatever
    the counterparty asked.
    """
    if buy_max_inr_per_kwh is None or sell_min_inr_per_kwh is None:
        return False
    return sell_min_inr_per_kwh <= buy_max_inr_per_kwh


def quantize_price(value: Decimal) -> Decimal:
    """Round a price to the stored precision.

    Half-up rather than banker's rounding: money owed to a participant should
    round predictably, and half-even would make two economically identical
    trades settle at different prices depending on the parity of a digit.
    """
    return value.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)

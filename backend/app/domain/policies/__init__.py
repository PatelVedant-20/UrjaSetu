"""Business policies — pure, deterministic decision logic.

Nothing here performs I/O or imports persistence, transport or adapter code
(docs/03_REPOSITORY_STRUCTURE.md).
"""

from app.domain.policies.audit_chain import (
    canonical_json,
    event_fingerprint,
    seal,
    verify_chain,
)
from app.domain.policies.clearing_price import (
    PriceCrossError,
    midpoint_clearing_price,
    prices_cross,
    quantize_price,
)
from app.domain.policies.dynamic_pricing import (
    DEFAULT_ENGINE,
    DEFAULT_PARAMETERS,
    ComponentPricingEngine,
    PricingParameters,
    TariffBand,
)
from app.domain.policies.eligibility import (
    EligibilityDecision,
    EligibilityInput,
    VerificationEvidence,
    evaluate_eligibility,
    resolve_verification_level,
)
from app.domain.policies.grid_limits import (
    DEFAULT_LIMITS,
    decide,
    describe_missing_ratings,
    effective_status,
    evaluate_metrics,
    resolve_status,
    summarise,
)
from app.domain.policies.market_matching import (
    BaselineMatchingEngine,
    ContinuousDoubleAuctionMatchingEngine,
)
from app.domain.policies.settlement import (
    DEFAULT_CALCULATOR,
    DEFAULT_POLICY,
    SettlementPolicy,
    StandardSettlementCalculator,
    quantize_amount,
    quantize_energy,
    reconcile,
)
from app.domain.policies.surplus import (
    SurplusPoint,
    SurplusWindow,
    calculate_surplus,
)
from app.domain.policies.telemetry_quality import (
    DEFAULT_STALENESS_THRESHOLD,
    QualityAssessment,
    SeriesContext,
    classify_reading,
)

__all__ = [
    "canonical_json",
    "event_fingerprint",
    "seal",
    "verify_chain",
    "DEFAULT_CALCULATOR",
    "DEFAULT_ENGINE",
    "DEFAULT_LIMITS",
    "DEFAULT_PARAMETERS",
    "DEFAULT_POLICY",
    "BaselineMatchingEngine",
    "ComponentPricingEngine",
    "PricingParameters",
    "TariffBand",
    "ContinuousDoubleAuctionMatchingEngine",
    "DEFAULT_STALENESS_THRESHOLD",
    "EligibilityDecision",
    "EligibilityInput",
    "PriceCrossError",
    "QualityAssessment",
    "SeriesContext",
    "SettlementPolicy",
    "StandardSettlementCalculator",
    "SurplusPoint",
    "SurplusWindow",
    "VerificationEvidence",
    "calculate_surplus",
    "decide",
    "describe_missing_ratings",
    "effective_status",
    "evaluate_metrics",
    "resolve_status",
    "midpoint_clearing_price",
    "prices_cross",
    "quantize_amount",
    "quantize_energy",
    "quantize_price",
    "reconcile",
    "summarise",
    "classify_reading",
    "evaluate_eligibility",
    "resolve_verification_level",
]

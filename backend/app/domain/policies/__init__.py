"""Business policies — pure, deterministic decision logic.

Nothing here performs I/O or imports persistence, transport or adapter code
(docs/03_REPOSITORY_STRUCTURE.md).
"""

from app.domain.policies.eligibility import (
    EligibilityDecision,
    EligibilityInput,
    VerificationEvidence,
    evaluate_eligibility,
    resolve_verification_level,
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
    "DEFAULT_STALENESS_THRESHOLD",
    "EligibilityDecision",
    "EligibilityInput",
    "QualityAssessment",
    "SeriesContext",
    "SurplusPoint",
    "SurplusWindow",
    "VerificationEvidence",
    "calculate_surplus",
    "classify_reading",
    "evaluate_eligibility",
    "resolve_verification_level",
]

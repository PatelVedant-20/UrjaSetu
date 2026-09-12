"""Phase 3: provider selection.

docs/05_API_SPEC.md requires the provider to be chosen by configuration or
domain policy rather than hard-coded. These tests pin that the registry is the
only place a name becomes an implementation, and that it refuses ambiguity.
"""

from __future__ import annotations

import pytest

from app.core.errors import UnprocessableError
from app.services import forecast_registry
from tests.integration.phase3.conftest import StubProvider


@pytest.fixture(autouse=True)
def _isolated_registry() -> object:
    forecast_registry.clear_registry()
    yield
    forecast_registry.clear_registry()


def test_a_registered_provider_can_be_resolved_by_name() -> None:
    provider = StubProvider(name="baseline")
    forecast_registry.register_provider(provider)

    assert forecast_registry.get_provider("baseline") is provider


def test_unknown_provider_is_reported_with_what_is_available() -> None:
    forecast_registry.register_provider(StubProvider(name="baseline"))

    with pytest.raises(UnprocessableError) as exc:
        forecast_registry.get_provider("openstef")

    assert exc.value.code == "FORECAST_PROVIDER_NOT_REGISTERED"
    assert exc.value.details["available"] == ["baseline"]


def test_two_providers_cannot_claim_one_name() -> None:
    """Otherwise which algorithm ran would depend on import order."""
    forecast_registry.register_provider(StubProvider(name="baseline"))

    with pytest.raises(UnprocessableError) as exc:
        forecast_registry.register_provider(StubProvider(name="baseline", model_version="9"))

    assert exc.value.code == "FORECAST_PROVIDER_NAME_TAKEN"


def test_re_registering_the_same_instance_is_allowed() -> None:
    """Importing an adapter module twice must not explode."""
    provider = StubProvider(name="baseline")
    forecast_registry.register_provider(provider)
    forecast_registry.register_provider(provider)

    assert forecast_registry.available_providers() == ["baseline"]


def test_replacement_is_possible_but_must_be_explicit() -> None:
    forecast_registry.register_provider(StubProvider(name="baseline"))
    replacement = StubProvider(name="baseline", model_version="2.0")

    forecast_registry.register_provider(replacement, replace=True)

    assert forecast_registry.get_provider("baseline") is replacement


def test_several_providers_coexist() -> None:
    """The point of the boundary: many algorithms, one contract."""
    for name in ("baseline", "gradient-boost", "openstef"):
        forecast_registry.register_provider(StubProvider(name=name))

    assert forecast_registry.available_providers() == ["baseline", "gradient-boost", "openstef"]


def test_registry_holds_no_implementation_of_its_own() -> None:
    """Nothing is registered until an adapter registers itself."""
    assert forecast_registry.available_providers() == []

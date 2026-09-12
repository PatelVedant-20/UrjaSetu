"""Provider selection.

docs/05_API_SPEC.md requires the forecast provider to be "selected via
configuration/domain policy, not hard-coded in routers". This is the one place
a provider name becomes a provider instance.

Nothing here imports a provider implementation. Adapters register themselves,
so the registry — and therefore the service, and therefore market code — never
names a concrete algorithm. Adding an OpenSTEF, XGBoost or hosted-model
provider is a registration, not an edit to this file.
"""

from __future__ import annotations

from app.core.errors import UnprocessableError
from app.domain.interfaces.forecasting import ForecastProvider

_REGISTRY: dict[str, ForecastProvider] = {}


class ForecastProviderNotRegisteredError(UnprocessableError):
    """The configured provider name has no implementation registered."""

    code = "FORECAST_PROVIDER_NOT_REGISTERED"


def register_provider(provider: ForecastProvider, *, replace: bool = False) -> None:
    """Make a provider available for selection by name.

    Refuses to shadow an existing registration unless asked: two adapters
    silently claiming one name would make which algorithm ran depend on import
    order, and a stored forecast could then no longer be attributed.
    """
    name = provider.name
    if not replace and name in _REGISTRY and _REGISTRY[name] is not provider:
        raise ForecastProviderNotRegisteredError(
            f"A different provider is already registered as {name!r}.",
            code="FORECAST_PROVIDER_NAME_TAKEN",
            details={"provider": name},
        )
    _REGISTRY[name] = provider


def get_provider(name: str) -> ForecastProvider:
    """Resolve a provider by name."""
    provider = _REGISTRY.get(name)
    if provider is None:
        raise ForecastProviderNotRegisteredError(
            f"No forecast provider is registered as {name!r}.",
            details={"provider": name, "available": sorted(_REGISTRY)},
        )
    return provider


def available_providers() -> list[str]:
    """Registered provider names, for diagnostics and `/api/v1/meta`."""
    return sorted(_REGISTRY)


def clear_registry() -> None:
    """Empty the registry. For tests; never call it from application code."""
    _REGISTRY.clear()

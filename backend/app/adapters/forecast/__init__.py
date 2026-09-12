"""Forecast adapters.

Implementations of `app.domain.interfaces.forecasting.ForecastProvider`.

This package exports **no contract types**: the request, result, point and
provider protocol all live in the domain, and re-exporting them here would
invite a second definition to grow (docs/03_REPOSITORY_STRUCTURE.md: no
duplicate domain abstractions).

`register_default_providers()` is the bridge from configuration to
implementation. It is called explicitly at application startup rather than run
as an import side effect, so importing an adapter never silently mutates global
state and tests can control registration.
"""

from __future__ import annotations

from app.adapters.forecast.baseline import BaselineForecastProvider
from app.services.forecast_registry import register_provider

__all__ = ["BaselineForecastProvider", "register_default_providers"]


def register_default_providers(*, replace: bool = False) -> None:
    """Register every provider this build ships with.

    Adding a provider is a line here, not a change to the forecasting service:
    the service only ever asks the registry for a name.
    """
    register_provider(BaselineForecastProvider(), replace=replace)

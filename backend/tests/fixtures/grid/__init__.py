"""Grid fixtures package for UrjaSetu Phase 5.

Exports loader functions that consume canonical grid contracts and models.
"""

from tests.fixtures.grid.loader import (
    build_canonical_network_model,
    build_canonical_validation_request,
    get_expected_decision,
    get_expected_validation_result,
    get_grid_fixtures_dir,
    list_available_grid_scenarios,
    load_grid_fixture,
    load_grid_manifest,
)

__all__ = [
    "build_canonical_network_model",
    "build_canonical_validation_request",
    "get_expected_decision",
    "get_expected_validation_result",
    "get_grid_fixtures_dir",
    "list_available_grid_scenarios",
    "load_grid_fixture",
    "load_grid_manifest",
]

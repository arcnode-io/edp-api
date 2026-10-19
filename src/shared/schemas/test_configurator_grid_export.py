"""Utility resolution and export-limit rules on the grid shape."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.configurator_grid_test_support import (
    _firm_grid,
    _grid_revenue_grid,
)

# --- V5a: non-off_grid requires resolution ---


def test_non_off_grid_requires_wires_owner_and_market_region() -> None:
    with pytest.raises(ValidationError, match="requires wires_owner and market_region"):
        _firm_grid(wires_owner=None)


# --- EX: export_limit_mw <-> export_mode=limited_export ---


def test_export_limit_required_when_limited_export() -> None:
    with pytest.raises(
        ValidationError, match="required iff export_mode=limited_export"
    ):
        _grid_revenue_grid(export_limit_mw=None)


def test_export_limit_forbidden_when_not_limited_export() -> None:
    with pytest.raises(
        ValidationError, match="required iff export_mode=limited_export"
    ):
        _firm_grid(export_limit_mw=5.0)


def test_export_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="must be > 0"):
        _grid_revenue_grid(export_limit_mw=-5.0)

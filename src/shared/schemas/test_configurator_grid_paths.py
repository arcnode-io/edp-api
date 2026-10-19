"""Grid path shape rules: off grid, flexible, firm, grid revenue, export limit."""

import pytest
from pydantic import ValidationError

from src.shared.enums import (
    ExportMode,
    GridPath,
    MarketProgram,
    MarketRegion,
    ServiceType,
)
from src.shared.schemas.configurator_grid_test_support import (
    _FLEX,
    _grid,
    _flexible_grid,
    _firm_grid,
    _grid_revenue_grid,
)

# --- Grid: off_grid (V1) ---


def test_off_grid_happy_path() -> None:
    grid = _grid()
    assert grid.path == GridPath.OFF_GRID
    assert grid.market_region is None


def test_off_grid_rejects_nonnull_market_region() -> None:
    with pytest.raises(ValidationError, match="to be null/default"):
        _grid(market_region=MarketRegion.ERCOT)


def test_off_grid_rejects_intentional_islanding() -> None:
    with pytest.raises(ValidationError, match="to be null/default"):
        _grid(intentional_islanding=True)


# --- Grid: flexible (V2) ---


def test_flexible_happy_path() -> None:
    grid = _flexible_grid()
    assert grid.service_type == ServiceType.FLEXIBLE


def test_flexible_rejects_wrong_service_type() -> None:
    with pytest.raises(ValidationError, match="requires service_type=flexible"):
        _flexible_grid(service_type=ServiceType.FIRM)


def test_flexible_rejects_missing_flex_obligation() -> None:
    with pytest.raises(ValidationError, match="flex_obligation set iff flexible"):
        _flexible_grid(flex_obligation=None)


def test_flexible_rejects_export_mode_set() -> None:
    with pytest.raises(ValidationError, match="requires export_mode=non_export"):
        _flexible_grid(export_mode=ExportMode.LIMITED_EXPORT, export_limit_mw=5.0)


# --- Grid: firm (V3) ---


def test_firm_happy_path() -> None:
    grid = _firm_grid()
    assert grid.service_type == ServiceType.FIRM
    assert grid.flex_obligation is None


def test_firm_rejects_flex_obligation_present() -> None:
    with pytest.raises(ValidationError, match="flex_obligation set iff flexible"):
        _firm_grid(flex_obligation=_FLEX)


# --- Grid: grid_revenue (V4a) ---


def test_grid_revenue_happy_path() -> None:
    grid = _grid_revenue_grid()
    assert grid.market_program == MarketProgram.ERCOT_ADER


def test_grid_revenue_rejects_non_export() -> None:
    with pytest.raises(ValidationError, match="requires export_mode != non_export"):
        _grid_revenue_grid(export_mode=ExportMode.NON_EXPORT, export_limit_mw=None)


def test_grid_revenue_rejects_missing_settlement_point() -> None:
    with pytest.raises(ValidationError, match="requires settlement_point"):
        _grid_revenue_grid(settlement_point=None)


def test_grid_revenue_rejects_flex_obligation_mismatch() -> None:
    """service_type=firm but flex_obligation still set — must be null for firm."""
    with pytest.raises(ValidationError, match="flex_obligation iff flexible"):
        _grid_revenue_grid(service_type=ServiceType.FIRM, flex_obligation=_FLEX)

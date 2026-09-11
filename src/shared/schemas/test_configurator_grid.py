"""Unit tests for Site/OnsiteGeneration/WiresOwner/FlexObligation/Grid validators."""

import pytest
from pydantic import ValidationError

from src.shared.enums import (
    ExportMode,
    FlexLevel,
    GridPath,
    MarketAccess,
    MarketProgram,
    MarketRegion,
    OnsiteGenerationType,
    ServiceType,
    WiresOwnerType,
)
from src.shared.schemas.configurator_grid import (
    FlexObligation,
    Grid,
    OnsiteGeneration,
    Site,
    SiteLocation,
    WiresOwner,
)

_WIRES_OWNER = WiresOwner(
    id="oncor", name="Oncor Electric Delivery", type=WiresOwnerType.TDSP
)
_FLEX = FlexObligation(
    level=FlexLevel.STANDARD,
    depth_pct=50.0,
    max_duration_h=4.0,
    max_events_yr=40,
    min_interval_h=20.0,
    notice_s=600,
)


def _grid(
    *, market_region: MarketRegion | None = None, intentional_islanding: bool = False
) -> Grid:
    """Valid off_grid Grid by default."""
    return Grid(
        path=GridPath.OFF_GRID,
        market_region=market_region,
        intentional_islanding=intentional_islanding,
    )


def _flexible_grid(
    *,
    service_type: ServiceType = ServiceType.FLEXIBLE,
    flex_obligation: FlexObligation | None = _FLEX,
    export_mode: ExportMode = ExportMode.NON_EXPORT,
    export_limit_mw: float | None = None,
) -> Grid:
    """Valid flexible-path Grid by default."""
    return Grid(
        path=GridPath.FLEXIBLE,
        service_type=service_type,
        flex_obligation=flex_obligation,
        export_mode=export_mode,
        export_limit_mw=export_limit_mw,
        wires_owner=_WIRES_OWNER,
        market_region=MarketRegion.ERCOT,
    )


def _firm_grid(
    *,
    flex_obligation: FlexObligation | None = None,
    wires_owner: WiresOwner | None = _WIRES_OWNER,
    export_limit_mw: float | None = None,
) -> Grid:
    """Valid firm-path Grid by default."""
    return Grid(
        path=GridPath.FIRM,
        service_type=ServiceType.FIRM,
        flex_obligation=flex_obligation,
        wires_owner=wires_owner,
        market_region=MarketRegion.ERCOT,
        export_limit_mw=export_limit_mw,
    )


def _grid_revenue_grid(
    *,
    service_type: ServiceType = ServiceType.FLEXIBLE,
    flex_obligation: FlexObligation | None = _FLEX,
    export_mode: ExportMode = ExportMode.LIMITED_EXPORT,
    export_limit_mw: float | None = 5.0,
    settlement_point: str | None = "HB_NORTH",
) -> Grid:
    """Valid grid_revenue-path Grid by default."""
    return Grid(
        path=GridPath.GRID_REVENUE,
        service_type=service_type,
        flex_obligation=flex_obligation,
        export_mode=export_mode,
        export_limit_mw=export_limit_mw,
        market_access=MarketAccess.DIRECT,
        market_program=MarketProgram.ERCOT_ADER,
        settlement_point=settlement_point,
        wires_owner=_WIRES_OWNER,
        market_region=MarketRegion.ERCOT,
    )


# --- Site ---


def test_site_happy_path() -> None:
    # Arrange / Act
    site = Site(location=SiteLocation(lat=32.7, lon=-96.8), country="US", state="TX")
    # Assert
    assert site.country == "US"


def test_site_rejects_lowercase_country() -> None:
    with pytest.raises(ValidationError, match="uppercase 2-letter"):
        Site(location=SiteLocation(lat=32.7, lon=-96.8), country="us")


def test_site_rejects_non_2_char_country() -> None:
    with pytest.raises(ValidationError, match="uppercase 2-letter"):
        Site(location=SiteLocation(lat=32.7, lon=-96.8), country="USA")


# --- OnsiteGeneration (V7) ---


def test_onsite_generation_none_type_happy_path() -> None:
    gen = OnsiteGeneration(type=OnsiteGenerationType.NONE, capacity_mw=None)
    assert gen.capacity_mw is None


def test_onsite_generation_none_type_rejects_capacity() -> None:
    with pytest.raises(ValidationError, match="must be null when type=none"):
        OnsiteGeneration(type=OnsiteGenerationType.NONE, capacity_mw=5.0)


def test_onsite_generation_solar_requires_positive_capacity() -> None:
    gen = OnsiteGeneration(type=OnsiteGenerationType.SOLAR, capacity_mw=10.0)
    assert gen.capacity_mw == 10.0


def test_onsite_generation_solar_rejects_null_capacity() -> None:
    with pytest.raises(ValidationError, match="must be > 0 when type != none"):
        OnsiteGeneration(type=OnsiteGenerationType.SOLAR, capacity_mw=None)


def test_onsite_generation_solar_rejects_zero_capacity() -> None:
    with pytest.raises(ValidationError, match="must be > 0 when type != none"):
        OnsiteGeneration(type=OnsiteGenerationType.SOLAR, capacity_mw=0.0)


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

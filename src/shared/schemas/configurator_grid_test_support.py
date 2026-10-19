"""Grid builders for configurator grid tests; import explicitly."""

from src.shared.enums import (
    ExportMode,
    FlexLevel,
    GridPath,
    MarketAccess,
    MarketProgram,
    MarketRegion,
    ServiceType,
    WiresOwnerType,
)
from src.shared.schemas.configurator_grid import (
    FlexObligation,
    Grid,
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

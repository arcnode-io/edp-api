"""Region-dependent grid validation rules (V4b, V6, SP, FL).

These need config/grid_regions.yaml, so they can't be pydantic model_validators
(no I/O in validators). Called from JobsService.create and the sizing preview
endpoint before anything else touches the payload; raises ValueError on the
first violation, which the caller maps to a 422.
"""

from src.shared.enums import ExportMode, FlexLevel, GridPath, MarketRegion
from src.shared.schemas.configurator_grid import FlexObligation, Grid
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.grid_regions import GridRegionsConfig


def validate_against_regions(
    payload: ConfiguratorPayload, regions: GridRegionsConfig
) -> None:
    """Raise ValueError on the first region-dependent rule violation."""
    grid = payload.grid
    _check_market_program(grid, regions)
    _check_export_limit(grid, regions)
    _check_settlement_point(grid, regions)
    check_flex_preset(grid.flex_obligation, regions)


def _check_market_program(grid: Grid, regions: GridRegionsConfig) -> None:
    """V4b: grid_revenue's market_program must be one the region actually offers."""
    if grid.path != GridPath.GRID_REVENUE or grid.market_region is None:
        return
    allowed = regions.regions[grid.market_region].market_programs
    if grid.market_program not in allowed:
        raise ValueError(
            f"market_program={grid.market_program} not offered in "
            f"{grid.market_region.value} (allowed: {[p.value for p in allowed]})"
        )


def _check_export_limit(grid: Grid, regions: GridRegionsConfig) -> None:
    """V6: ERCOT limited-export can't exceed the DG export cap."""
    if (
        grid.market_region != MarketRegion.ERCOT
        or grid.export_mode != ExportMode.LIMITED_EXPORT
    ):
        return
    cap = regions.regions[MarketRegion.ERCOT].dg_export_max_mw
    if (
        cap is not None
        and grid.export_limit_mw is not None
        and grid.export_limit_mw > cap
    ):
        raise ValueError(
            f"export_limit_mw={grid.export_limit_mw} exceeds ERCOT dg_export_max_mw={cap}"
        )


def _check_settlement_point(grid: Grid, regions: GridRegionsConfig) -> None:
    """SP: settlement_point only valid for ERCOT, and must be a known point."""
    if grid.settlement_point is None:
        return
    if grid.market_region != MarketRegion.ERCOT:
        raise ValueError("settlement_point is only valid for market_region=ercot")
    allowed = regions.regions[MarketRegion.ERCOT].settlement_points
    if grid.settlement_point not in allowed:
        raise ValueError(f"settlement_point={grid.settlement_point!r} not in {allowed}")


def check_flex_preset(fx: FlexObligation | None, regions: GridRegionsConfig) -> None:
    """FL (D12): non-custom flex level's five numbers must equal the yaml preset.

    Shared with the sizing preview endpoint (src/sizing/) — SizingGridInput
    carries a flex_obligation too, so both call sites reuse this check
    instead of duplicating it.
    """
    if fx is None or fx.level == FlexLevel.CUSTOM:
        return
    preset = regions.flex_levels[fx.level]
    actual = (
        fx.depth_pct,
        fx.max_duration_h,
        fx.max_events_yr,
        fx.min_interval_h,
        fx.notice_s,
    )
    expected = (
        preset.depth_pct,
        preset.max_duration_h,
        preset.max_events_yr,
        preset.min_interval_h,
        preset.notice_s,
    )
    if actual != expected:
        raise ValueError(
            f"flex_obligation.level={fx.level.value} numbers must match preset "
            f"{expected}, got {actual}"
        )

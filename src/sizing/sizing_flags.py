"""Sizing preview flags (§5.5) — split out of sizing_internals.py (200-line budget).

Distinct concern from the physics in sizing_internals.py: this is "what
should the operator be told", not "what are the numbers". Table-driven
(condition, code, level, message) rather than a long if-chain — keeps
cyclomatic complexity down and makes each rule a one-line, auditable row.
"""

from src.shared.enums import ExportMode, GridPath, MarketRegion, ServiceType
from src.shared.schemas.sizing import (
    LimitState,
    SizingFlag,
    SizingFlagCode,
    SizingFlagLevel,
    SizingGridInput,
)


def compute_flags(
    *,
    grid: SizingGridInput,
    limit_state: LimitState,
    effective_service_type: ServiceType | None,
    bess_coupling_is_none: bool,
    usable_mwh: float,
    e_reserve_mwh: float,
    e_min_usable_mwh: float | None,
    ride_through_hours: float,
) -> list[SizingFlag]:
    """§5.5. path/export_mode=None means "not yet chosen" — not-applicable,
    not a specific value, so the corresponding rows don't fire."""
    is_flexible = effective_service_type == ServiceType.FLEXIBLE
    known_non_off_grid = grid.path is not None and grid.path != GridPath.OFF_GRID
    flex_bess_shortfall = (
        is_flexible
        and not bess_coupling_is_none
        and e_min_usable_mwh is not None
        and usable_mwh < e_min_usable_mwh
    )
    warn, info = SizingFlagLevel.WARN, SizingFlagLevel.INFO
    rows: list[tuple[bool, SizingFlagCode, SizingFlagLevel, str]] = [
        (
            limit_state == LimitState.OVER and known_non_off_grid,
            SizingFlagCode.TRANSMISSION_MANUAL_ENGAGEMENT,
            warn,
            "This site needs transmission-level service — we'll engage directly.",
        ),
        (
            limit_state == LimitState.NEAR,
            SizingFlagCode.NEAR_DISTRIBUTION_LIMIT,
            info,
            "Close to the distribution service limit.",
        ),
        (
            flex_bess_shortfall,
            SizingFlagCode.FLEX_BESS_SHORTFALL,
            warn,
            "BESS capacity is below what flexible service requires.",
        ),
        (
            is_flexible and bess_coupling_is_none,
            SizingFlagCode.FLEX_NO_BESS,
            warn,
            "Flexible service needs a battery to protect your GPUs.",
        ),
        (
            is_flexible,
            SizingFlagCode.RECHARGE_HEADROOM,
            info,
            "Recharge power is added on top of your grid peak.",
        ),
        (
            ride_through_hours > 0 and usable_mwh < e_reserve_mwh,
            SizingFlagCode.RESERVE_SHORTFALL,
            warn,
            "BESS capacity is below the ride-through reserve you requested.",
        ),
        (
            grid.export_mode is not None and grid.export_mode != ExportMode.NON_EXPORT,
            SizingFlagCode.EXPORT_REVIEW,
            info,
            "Export configuration will be reviewed during interconnection.",
        ),
        (
            grid.market_region == MarketRegion.ERCOT
            and grid.export_mode == ExportMode.EXPORT,
            SizingFlagCode.EXPORT_PCS_RATING_UNVERIFIED,
            warn,
            "Full export PCS rating isn't verified numerically yet.",
        ),
        (
            grid.export_mode == ExportMode.NON_EXPORT and known_non_off_grid,
            SizingFlagCode.NON_EXPORT_TRANSIENT_UNVERIFIED,
            warn,
            "Non-export transient behavior isn't verified numerically yet.",
        ),
        (
            grid.intentional_islanding,
            SizingFlagCode.ISLANDING_REVIEW_REQUIRED,
            warn,
            "Intentional islanding requires utility review.",
        ),
        (
            grid.intentional_islanding,
            SizingFlagCode.ISLANDING_TRANSFER_UNVERIFIED,
            warn,
            "Transfer-switch behavior for islanding isn't verified yet.",
        ),
    ]
    return [
        SizingFlag(code=code, level=level, message=message)
        for fires, code, level, message in rows
        if fires
    ]

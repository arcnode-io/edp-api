"""Pure sizing math — no I/O, no pydantic model_validators. Split out of
sizing_service.py for the 200-line budget (mirrors dtm_generator_service.py /
dtm_generator_internals.py).
"""

from math import ceil
from typing import Final

from src.shared.enums import (
    DeploymentContext,
    GridPath,
    InterconnectionLevel,
    MarketRegion,
    OnsiteGenerationType,
    ServiceType,
)
from src.shared.schemas.configurator_grid import FlexObligation, OnsiteGeneration
from src.shared.schemas.grid_regions import RegionDefaults
from src.shared.schemas.sizing import FlexPreview, LimitState, SizingGridInput

ETA_D: Final[float] = 0.95  # [OPEN] per BESS OEM
ETA_C: Final[float] = 0.95  # [OPEN] per BESS OEM

# GRD-XFM-001 Trihal rating. Each grid container carries one transformer.
# Reason: kW ~ kVA here; the HGX PSUs run near unity power factor.
GRID_CONTAINER_KVA: Final[float] = 1000.0
# ADR-021: continuous design load is 80% of nameplate. The Trihal sits in a
# closed container on natural convection with no overhead margin (ADR-013).
TRANSFORMER_DESIGN_LOADING: Final[float] = 0.8


def grid_container_count(site_peak: float) -> int:
    """One grid container per 800 kVA of site load (ADR-021)."""
    return ceil(site_peak * 1000 / (GRID_CONTAINER_KVA * TRANSFORMER_DESIGN_LOADING))


def firm_onsite_mw(onsite_generation: OnsiteGeneration) -> float:
    """Nuclear capacity counts as firm; solar counts 0; none -> 0."""
    if onsite_generation.type == OnsiteGenerationType.NUCLEAR:
        return onsite_generation.capacity_mw or 0.0
    return 0.0


def grid_peak_mw(*, site_peak: float, firm_onsite: float) -> float:
    """max(0, site_peak_mw - firm_onsite_mw)."""
    return max(0.0, site_peak - firm_onsite)


def interconnection_level(
    grid_peak: float, defaults: RegionDefaults
) -> InterconnectionLevel:
    """5.2: distribution if grid_peak <= the limit, else transmission."""
    if grid_peak <= defaults.distribution_limit_mw:
        return InterconnectionLevel.DISTRIBUTION
    return InterconnectionLevel.TRANSMISSION


def limit_state(grid_peak: float, defaults: RegionDefaults) -> LimitState:
    """5.2: over > limit; near >= near-threshold; else within."""
    if grid_peak > defaults.distribution_limit_mw:
        return LimitState.OVER
    if grid_peak >= defaults.distribution_near_mw:
        return LimitState.NEAR
    return LimitState.WITHIN


def recommend(
    *,
    deployment_context: DeploymentContext,
    market_region: MarketRegion | None,
    limit_state: LimitState,
    grid_peak_mw: float,
) -> tuple[GridPath | None, str]:
    """5.3: first match wins."""
    if deployment_context == DeploymentContext.DEFENSE_FORWARD:
        return GridPath.OFF_GRID, "Recommended for forward deployments."
    if market_region is None:
        return (
            GridPath.OFF_GRID,
            "We can't identify a utility here yet — off-grid is available.",
        )
    if limit_state != LimitState.OVER:
        return (
            GridPath.FLEXIBLE,
            f"{grid_peak_mw:.1f} MW fits distribution service; "
            "flexible service is the fastest path.",
        )
    return (
        None,
        "Sites this size need transmission-level service. "
        "We'll engage directly after you submit.",
    )


def effective_service_type(grid: SizingGridInput) -> ServiceType | None:
    """grid.service_type if given, else flexible when path=flexible, else null."""
    if grid.service_type is not None:
        return grid.service_type
    if grid.path == GridPath.FLEXIBLE:
        return ServiceType.FLEXIBLE
    return None


def reserve_mwh(*, ride_through_hours: float, grid_peak_mw: float) -> float:
    """[A1] E_r = ride_through_hours * P_g / ETA_D. Always computed, flex or not."""
    return ride_through_hours * grid_peak_mw / ETA_D


def bess_min_mwh(*, e_reserve_mwh: float, e_flex_mwh: float | None) -> float:
    """[A1] e_reserve_mwh + (e_flex_mwh if effective service_type is flexible else 0)."""
    return e_reserve_mwh + (e_flex_mwh or 0.0)


def flex_energy_mwh(*, grid_peak_mw: float, flex_obligation: FlexObligation) -> float:
    """5.4 E_flex = d * P_g * t_e / ETA_D — energy to ride one curtailment event."""
    d = flex_obligation.depth_pct / 100
    return d * grid_peak_mw * flex_obligation.max_duration_h / ETA_D


def recharge_mw(*, e_flex_mwh: float, flex_obligation: FlexObligation) -> float:
    """5.4 P_recharge = E_flex / (ETA_C * t_i) — refill before the next event."""
    return e_flex_mwh / (ETA_C * flex_obligation.min_interval_h)


def flex_preview(
    *,
    grid_peak_mw: float,
    flex_obligation: FlexObligation,
    e_reserve_mwh: float,
    usable_mwh: float,
) -> FlexPreview:
    """5.4, only called when effective service_type == flexible."""
    d = flex_obligation.depth_pct / 100
    t_e = flex_obligation.max_duration_h
    e_flex = flex_energy_mwh(grid_peak_mw=grid_peak_mw, flex_obligation=flex_obligation)
    e_min_usable = e_reserve_mwh + e_flex
    p_recharge = recharge_mw(e_flex_mwh=e_flex, flex_obligation=flex_obligation)
    p_contract = grid_peak_mw + p_recharge
    if d * grid_peak_mw == 0:
        bess_covers_h = t_e
    else:
        # [A1] reserve is held back from curtailment coverage.
        bess_covers_h = min(
            t_e, max(0.0, usable_mwh - e_reserve_mwh) * ETA_D / (d * grid_peak_mw)
        )
    gpu_cap_pct = (1 - d) * 100 if bess_covers_h < t_e else None
    return FlexPreview(
        e_flex_mwh=e_flex,
        e_min_usable_mwh=e_min_usable,
        p_contract_mw=p_contract,
        p_recharge_mw=p_recharge,
        bess_covers_h=bess_covers_h,
        gpu_cap_pct_during_shortfall=gpu_cap_pct,
    )

"""Pure sizing math — no I/O, no pydantic model_validators. Split out of
sizing_service.py for the 200-line budget (mirrors dtm_generator_service.py /
dtm_generator_internals.py).
"""

from math import ceil
from typing import Final

from src.module_resolver.deployment_profile import GPUS_PER_COMPUTE_CONTAINER
from src.shared.enums import (
    BessCoupling,
    DeploymentContext,
    GpuVariant,
    GridPath,
    InterconnectionLevel,
    MarketRegion,
    OnsiteGenerationType,
    ServiceType,
)
from src.shared.schemas.configurator_grid import FlexObligation, OnsiteGeneration
from src.shared.schemas.grid_regions import RegionDefaults
from src.shared.schemas.sizing import FlexPreview, LimitState, SizingGridInput

# source: edp-module-assemblies/equipment/CMP-NODE-001/spec.yaml
# confidence_flags note on spec.electrical.power_kw. B200 first-principles:
# 8x1000W GPU + 2x350W CPU + 32x9W RAM + 8x12W NVMe + 8x35W NIC + 2x75W DPU +
# ~5% VRM (450W) + 150W fans/BMC/misc = 10,114W internal / 0.96 PSU efficiency
# = 10.5 kW/node. Container = 7 nodes x 10.5 + ~7kW switch/CDU/PDU overhead
# = 80 kW (CONTRACT §5.1, fixed).
#
# H100_SXM derived the same way, swapping only GPU TDP (700W vs 1000W):
# 8x700W GPU + same 700+288+96+280+150=1514W non-GPU + ~5% VRM (356W of the
# 7114W pre-VRM subtotal) + 150W fans/BMC = 7,620W internal / 0.96 = 7.94
# kW/node. Container = 7 x 7.94 + ~7kW overhead = 62.6 kW.
# [OPEN: PM/PO to confirm — derived by TDP substitution, not a real H100_SXM
# node datasheet; no such spec exists in edp-module-assemblies yet.]
CONTAINER_KW: Final[dict[GpuVariant, float]] = {
    GpuVariant.B200: 80.0,
    GpuVariant.H100_SXM: 62.6,
}

ETA_D: Final[float] = 0.95  # [OPEN] per BESS OEM
ETA_C: Final[float] = 0.95  # [OPEN] per BESS OEM


def site_peak_mw(gpu_variant: GpuVariant, target_gpu_count: int) -> float:
    """5.1: compute_containers * container_kw / 1000."""
    containers = ceil(target_gpu_count / GPUS_PER_COMPUTE_CONTAINER)
    return containers * CONTAINER_KW[gpu_variant] / 1000


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
    bess_coupling: BessCoupling,
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
    if limit_state != LimitState.OVER and bess_coupling != BessCoupling.NONE:
        return (
            GridPath.FLEXIBLE,
            f"{grid_peak_mw:.1f} MW fits distribution service; "
            "flexible service is the fastest path.",
        )
    if limit_state != LimitState.OVER and bess_coupling == BessCoupling.NONE:
        return GridPath.FIRM, "Flexible service needs a battery to protect your GPUs."
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
    t_i = flex_obligation.min_interval_h
    e_flex = d * grid_peak_mw * t_e / ETA_D
    e_min_usable = e_reserve_mwh + e_flex
    p_recharge = e_flex / (ETA_C * t_i)
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

"""The DTM's sizing block — split from dtm_generator_internals (200-line budget)."""

from typing import Final

from src.shared.schemas.dtm import SizingParams
from src.shared.schemas.module_resolution import ModuleResolution
from src.sizing.compute_nodes import site_peak_mw
from src.sizing.sizing_internals import (
    firm_onsite_mw,
    flex_energy_mwh,
    grid_peak_mw,
    recharge_mw,
    reserve_mwh,
)

_T_COOLANT_SETPOINT_C: Final[float] = 30.0


def sizing(resolution: ModuleResolution) -> SizingParams:
    """Compute SizingParams from resolution.

    Reason: compute load and bess_reserve_floor_mwh both come from the same
    pure sizing math the configurator's sizing-preview endpoint uses
    (site_peak = servers x node kW + per-container overhead) — one figure,
    so the load the reserve is sized against is the load the DTM declares, and
    both match what the operator already saw in preview.
    """
    peak = site_peak_mw(resolution.gpu_variant, resolution.gpu_count)
    firm = firm_onsite_mw(resolution.onsite_generation)
    g_peak = grid_peak_mw(site_peak=peak, firm_onsite=firm)
    e_reserve = reserve_mwh(
        ride_through_hours=resolution.ride_through_hours, grid_peak_mw=g_peak
    )
    # Reason: Grid guarantees flex_obligation is set iff the path is flexible.
    flex = resolution.grid.flex_obligation
    e_flex = (
        0.0
        if flex is None
        else flex_energy_mwh(grid_peak_mw=g_peak, flex_obligation=flex)
    )
    p_recharge = (
        0.0 if flex is None else recharge_mw(e_flex_mwh=e_flex, flex_obligation=flex)
    )
    return SizingParams(
        P_compute_total_kW=peak * 1000,
        E_BESS_total_kWh=resolution.bess_capacity_mwh * 1000,
        T_coolant_setpoint_C=_T_COOLANT_SETPOINT_C,
        ride_through_hours=resolution.ride_through_hours,
        bess_reserve_floor_mwh=e_reserve,
        compute_shed_enabled=resolution.compute_shed_enabled,
        bess_readiness_mwh=e_reserve + e_flex,
        bess_recharge_mw=p_recharge,
    )

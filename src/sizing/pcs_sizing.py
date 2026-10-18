"""dc_ext PCS fleet sized to the battery's power job (pure math, no I/O).

The PCS meets the load only on the 13.8 kV bus (ADR-022), so its count
follows what the battery is asked to deliver there, not the grid containers.
"""

from math import ceil
from typing import Final

from src.shared.enums import ExportMode, GridPath
from src.shared.schemas.configurator_grid import FlexObligation, Grid
from src.shared.schemas.sizing import SizingGridInput
from src.sizing.sizing_internals import flex_energy_mwh, recharge_mw

# GRD-PCS-001 EPC CAB1000: 1043 kW at 480 V, 40 °C, PF 1
PCS_KW: Final[float] = 1043.0
# EXT-BESS-002 CATL EnerOne+ rack: 379.4 kWh at 1C, so 379.4 kW
CATL_RACK_KWH: Final[float] = 379.4
CATL_RACK_KW: Final[float] = 379.4


def bess_power_need_mw(
    *,
    grid_peak_mw: float,
    ride_through_hours: float,
    grid: Grid | SizingGridInput,
    flex: FlexObligation | None,
    bess_capacity_mwh: float,
) -> float:
    """Largest AC power the battery is asked for, MW, over every job it has.

    Jobs: carry the site (ride-through or off grid), curtail d·P_g and refill
    at P_recharge (flex), export to the limit, or export the whole battery.
    No job (firm, no ride-through, no export) → 0.

    Args:
        flex: The obligation in force; passed apart from `grid` because the
            preview falls back to the standard preset when grid has none.
    """
    jobs = [0.0]
    if ride_through_hours > 0 or grid.path == GridPath.OFF_GRID:
        jobs.append(grid_peak_mw)
    if flex is not None:
        e_flex = flex_energy_mwh(grid_peak_mw=grid_peak_mw, flex_obligation=flex)
        jobs.append(flex.depth_pct / 100 * grid_peak_mw)
        jobs.append(recharge_mw(e_flex_mwh=e_flex, flex_obligation=flex))
    match grid.export_mode:
        case ExportMode.LIMITED_EXPORT:
            # Reason: a preview may not know the limit yet; the order always does
            jobs.append(grid.export_limit_mw or 0.0)
        case ExportMode.EXPORT:
            jobs.append(bess_dc_power_mw(bess_capacity_mwh))
    return max(jobs)


def pcs_count(p_need_mw: float) -> int:
    """PCS units to carry p_need_mw; at least one so the battery connects."""
    # Reason: round off float noise so 1.043 MW is one unit, not two
    return max(1, ceil(round(p_need_mw * 1000 / PCS_KW, 6)))


def bess_dc_power_mw(bess_capacity_mwh: float) -> float:
    """DC power of the CATL bank: whole racks for the ordered energy, at 1C."""
    racks = ceil(round(bess_capacity_mwh * 1000 / CATL_RACK_KWH, 6))
    return racks * CATL_RACK_KW / 1000

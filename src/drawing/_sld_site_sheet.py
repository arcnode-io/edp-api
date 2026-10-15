"""SLD sheet 1 — site one-line: utility → 13.8 kV site bus → BESS + grid containers.

Every battery ties in at 13.8 kV through customer gear (ADR-016); on dc_ext
it's the CATL strings behind ARCNODE's PCS, one per grid container (ADR-022).

Fixed size whatever the order: G1 (primary) is drawn, and G2-GM once as
typical. The POI meter sits on the utility service (ADR-020). Each grid container's compute feeders are drawn
as one feeder marked with the containers it stands for (ADR-018).
"""

from ezdxf.layouts import Modelspace

from src.bom_generator.bom_models import Bom
from src.drawing import _draw_kit as k
from src.sizing.compute_feeds import compute_feeds
from src.sizing.sizing_internals import GRID_CONTAINER_KVA

_MV_BUS_Y: float = 250.0
_LV_BUS_Y: float = 188.0


def draw_site_sheet(msp: Modelspace, bom: Bom) -> None:
    """Draw the site one-line for this BOM's container counts + coupling."""
    feeds = compute_feeds(bom.compute_container_qty, bom.grid_container_qty)

    k.source(msp, 40, 272)
    k.text(msp, 48, 272, "UTILITY SERVICE 13.8 kV 3PH 60 Hz", h=2.5)
    k.wire(msp, (40, 267), (40, _MV_BUS_Y))
    k.meter(msp, 40, 261)
    k.text(msp, 56, 262.5, "POI METER GRD-MTR-001 AT UTILITY SERVICE (ADR-020)", h=2.0)
    k.text(msp, 56, 259, "CTs/PTs + INSTALL BY OTHERS", h=2.0)
    k.bus(msp, 30, 390, _MV_BUS_Y, "13.8 kV SITE BUS — BY OTHERS (ADR-018)", 46)

    dc_ext = bom.profile.endswith("dc_ext")
    _mv_battery(msp, 60, bom)
    _grid_column(msp, 175.0, "GRID CONTAINER G1 (PRIMARY)", feeds[0])
    rest = [n for feed in feeds[1:] for n in feed]
    if bom.grid_container_qty > 1:
        m = bom.grid_container_qty
        title = (
            "GRID CONTAINER G2"
            if m == 2
            else f"GRID CONTAINERS G2-G{m} (TYPICAL OF {m - 1})"
        )
        _grid_column(msp, 300.0, title, rest)
    _notes(msp, dc_ext)
    k.equipment_list(msp, bom, _equipment(dc_ext), 15, 95)


def _equipment(dc_ext: bool) -> list[str]:
    ids = ["GRD-SWG-001", "GRD-RLY-001", "GRD-MTR-001", "GRD-XFM-001", "GRD-LVS-001"]
    return [*ids, "GRD-PCS-001"] if dc_ext else ids


def _mv_battery(msp: Modelspace, x: float, bom: Bom) -> None:
    """ADR-016/-022: the battery ties to the site bus through customer gear."""
    k.wire(msp, (x, _MV_BUS_Y), (x, 241))
    k.disconnect(msp, x, 238)
    k.text(msp, x + 6, 238, "MV DISCONNECT — BY OTHERS", h=2.0)
    k.wire(msp, (x, 235), (x, 225))
    k.transformer(msp, x, 220)
    k.text(msp, x + 6, 221.5, "T-BESS STEP-UP TO 13.8 kV", h=2.0)
    k.text(msp, x + 6, 218, "BY OTHERS", h=2.0)
    k.wire(msp, (x, 213), (x, 203))
    if not bom.profile.endswith("dc_ext"):
        battery = (
            "TESLA MEGAPACK 2 XL"
            if bom.profile.endswith("_ac")
            else "CATL WITH OWN PCS"
        )
        k.box(msp, x, 196, 44, 13, [battery, "CUSTOMER-SUPPLIED (ADR-016)"])
        return
    n = bom.grid_container_qty
    k.box(msp, x, 196, 44, 13, [f"GRD-PCS-001 x{n}", "ARCNODE PCS (ADR-022)"])
    k.wire(msp, (x, 189.5), (x, 181))
    k.text(msp, x + 4, 185, "DC", h=2.0)
    k.box(msp, x, 174, 44, 13, ["CATL ENERONE+ (DC)", "CUSTOMER-SUPPLIED"])


def _grid_column(
    msp: Modelspace,
    x: float,
    title: str,
    computes: list[int],
) -> None:
    """One grid container: MV breaker → Trihal → LV main → LV bus."""
    lx = x + 7  # label column
    k.wire(msp, (x, _MV_BUS_Y), (x, 240.5))
    k.breaker(msp, x, 238)
    k.text(msp, lx, 239.5, "52 MV BREAKER GRD-SWG-001", h=2.0)
    k.text(msp, lx, 236, "50/51 RELAY GRD-RLY-001", h=2.0)
    k.wire(msp, (x, 235.5), (x, 217))
    k.transformer(msp, x, 212)
    k.text(msp, lx, 214, "GRD-XFM-001", h=2.0)
    k.text(msp, lx, 210.5, f"{GRID_CONTAINER_KVA:.0f} kVA 13.8 kV - 415Y/240 V", h=2.0)
    k.wire(msp, (x, 205), (x, 199.5))
    k.breaker(msp, x, 197)
    k.text(msp, lx, 197, "LV MAIN GRD-LVS-001", h=2.0)
    k.wire(msp, (x, 194.5), (x, _LV_BUS_Y))
    k.bus(msp, x - 30, x + 50, _LV_BUS_Y, "415Y/240 V LV BUS", x + 3)

    fx = x - 15
    k.wire(msp, (fx, _LV_BUS_Y), (fx, 180.5))
    k.breaker(msp, fx, 178)
    k.wire(msp, (fx, 175.5), (fx, 168))
    k.box(msp, fx, 161, 34, 13, [_compute_label(computes), "FEEDER EACH · SHEET 2"])
    k.dashed_rect(msp, x - 38, 150, x + 75, 244)
    k.text(msp, x - 36, 152.5, title, h=2.2)


def _compute_label(computes: list[int]) -> str:
    if not computes:
        return "NO COMPUTE FEEDERS"
    first, last = computes[0], computes[-1]
    return f"COMPUTE C{first}" if first == last else f"COMPUTE C{first}-C{last}"


def _notes(msp: Modelspace, dc_ext: bool) -> None:
    battery = (
        "2. CATL strings feed ARCNODE's PCS (one per grid container); 13.8 kV via customer step-up (ADR-022)."
        if dc_ext
        else "2. AC-output BESS ties in at 13.8 kV through customer gear (ADR-016)."
    )
    notes = [
        "NOTES",
        "1. Compute containers split evenly over grid containers (ADR-018).",
        battery,
        "3. POI meter ships loose with G1, installed at the service (ADR-020).",
    ]
    for i, note in enumerate(notes):
        k.text(msp, 15, 52 - i * 5, note, h=2.5 if i == 0 else 2.2)

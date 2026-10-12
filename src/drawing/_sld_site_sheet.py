"""SLD sheet 1 — site one-line: utility → 13.8 kV site bus → BESS + grid containers.

Fixed size whatever the order: G1 (primary) is drawn, and G2-GM once as
typical. The POI meter sits on the utility service (ADR-020). Each grid container's compute feeders are drawn
as one feeder marked with the containers it stands for (ADR-018).
"""

from ezdxf.layouts import Modelspace

from src.bom_generator.bom_models import Bom
from src.drawing import _draw_kit as k
from src.drawing._one_line import compute_feeds
from src.sizing.sizing_internals import GRID_CONTAINER_KVA

_MV_BUS_Y: float = 250.0
_LV_BUS_Y: float = 188.0


def draw_site_sheet(msp: Modelspace, bom: Bom) -> None:
    """Draw the site one-line for this BOM's container counts + coupling."""
    dc_ext = bom.profile.endswith("dc_ext")
    feeds = compute_feeds(bom.compute_container_qty, bom.grid_container_qty)

    k.source(msp, 40, 272)
    k.text(msp, 48, 272, "UTILITY SERVICE 13.8 kV 3PH 60 Hz", h=2.5)
    k.wire(msp, (40, 267), (40, _MV_BUS_Y))
    k.meter(msp, 40, 261)
    k.text(msp, 56, 262.5, "POI METER GRD-MTR-001 AT UTILITY SERVICE (ADR-020)", h=2.0)
    k.text(msp, 56, 259, "CTs/PTs + INSTALL BY OTHERS", h=2.0)
    k.bus(msp, 30, 390, _MV_BUS_Y, "13.8 kV SITE BUS — BY OTHERS (ADR-018)", 46)

    g1_x, typ_x = (110.0, 270.0) if dc_ext else (175.0, 300.0)
    if not dc_ext:
        _mv_battery(msp, 60, bom.profile)
    _grid_column(msp, g1_x, "GRID CONTAINER G1 (PRIMARY)", feeds[0], dc_ext)
    rest = [n for feed in feeds[1:] for n in feed]
    if bom.grid_container_qty > 1:
        m = bom.grid_container_qty
        title = f"GRID CONTAINERS G2-G{m} (TYPICAL OF {m - 1})"
        _grid_column(msp, typ_x, title, rest, dc_ext)
    _notes(msp)
    k.equipment_list(msp, bom, _equipment(dc_ext), 15, 120)


def _equipment(dc_ext: bool) -> list[str]:
    ids = ["GRD-SWG-001", "GRD-RLY-001", "GRD-MTR-001", "GRD-XFM-001", "GRD-LVS-001"]
    return [*ids, "GRD-PCS-001"] if dc_ext else ids


def _mv_battery(msp: Modelspace, x: float, profile: str) -> None:
    """ADR-016: AC-output BESS ties to the site bus through customer gear."""
    battery = "TESLA MEGAPACK 2 XL" if profile.endswith("_ac") else "CATL WITH OWN PCS"
    k.wire(msp, (x, _MV_BUS_Y), (x, 241))
    k.disconnect(msp, x, 238)
    k.text(msp, x + 6, 238, "MV DISCONNECT — BY OTHERS", h=2.0)
    k.wire(msp, (x, 235), (x, 225))
    k.transformer(msp, x, 220)
    k.text(msp, x + 6, 220, "STEP-UP 13.8 kV / 480 V — BY OTHERS", h=2.0)
    k.wire(msp, (x, 213), (x, 203))
    k.box(msp, x, 196, 44, 13, [battery, "CUSTOMER-SUPPLIED (ADR-016)"])


def _grid_column(
    msp: Modelspace,
    x: float,
    title: str,
    computes: list[int],
    dc_ext: bool,
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
    if dc_ext:
        _pcs_branch(msp, x + 30)
    k.dashed_rect(msp, x - 38, 150, x + 75, 244)
    k.text(msp, x - 36, 152.5, title, h=2.2)


def _compute_label(computes: list[int]) -> str:
    if not computes:
        return "NO COMPUTE FEEDERS"
    first, last = computes[0], computes[-1]
    return f"COMPUTE C{first}" if first == last else f"COMPUTE C{first}-C{last}"


def _pcs_branch(msp: Modelspace, x: float) -> None:
    """dc_ext: PCS pair on the LV bus, CATL DC through BG-DC."""
    k.wire(msp, (x, _LV_BUS_Y), (x, 180.5))
    k.breaker(msp, x, 178)
    k.wire(msp, (x, 175.5), (x, 170))
    k.box(msp, x, 164, 30, 11, ["GRD-PCS-001 x2", "PD500 417 kW EA"])
    k.wire(msp, (x, 158.5), (x, 140))
    k.box(msp, x, 134, 36, 11, ["CATL ENERONE+ (DC)", "CUSTOMER-SUPPLIED · BG-DC"])


def _notes(msp: Modelspace) -> None:
    notes = [
        "NOTES",
        "1. Compute containers split evenly over grid containers (ADR-018).",
        "2. AC-output BESS ties in at 13.8 kV through customer gear (ADR-016).",
        "3. POI meter ships loose with G1, installed at the service (ADR-020).",
        "4. PART TBD: selection + fit pending (ADR-017, ADR-019).",
    ]
    for i, note in enumerate(notes):
        k.text(msp, 15, 52 - i * 5, note, h=2.5 if i == 0 else 2.2)

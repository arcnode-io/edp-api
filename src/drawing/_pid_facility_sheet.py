"""P&ID sheet 2 — facility (primary) coolant loop of one compute container, typical.

Closed loop: CDU primary return → through the CD plate → dry cooler
(ARCNODE-supplied, on the customer's pad) → pump → buffer tank (both by
others) → back through the CD plate → CDU primary supply. The CDU's
secondary ports run to off-sheet connectors (rack loop, sheet 1).
"""

from typing import Final

from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from src.drawing import _pid_kit as k
from src.drawing._pid_symbols import (
    ensure_buffer_tank_block,
    ensure_cdu_block,
    ensure_dry_cooler_block,
    ensure_pump_block,
)
from src.shared.schemas.dtm import Dtm

_CDU: Final[tuple[float, float]] = (300.0, 190.0)
_DRY_COOLER: Final[tuple[float, float]] = (70.0, 230.0)  # 50 x 30
_PUMP: Final[tuple[float, float]] = (145.0, 230.0)  # radius 6
_TANK: Final[tuple[float, float]] = (200.0, 230.0)  # 30 x 40
_WALL_X: Final[float] = 255.0
_SUPPLY_RISER_X: Final[float] = 270.0
_RETURN_DROP_X: Final[float] = 262.0
_RETURN_Y: Final[float] = 120.0
_RETURN_RISER_X: Final[float] = 30.0
_OFFSHEET_X: Final[float] = 330.0


def draw_facility_sheet(msp: Modelspace, doc: Drawing, dtm: Dtm) -> None:
    """Draw C1's primary loop, labelled typical of every compute container."""
    devices, n = k.typical_container(dtm)
    cdu = next((d for d in devices if d.template == "cdu"), None)
    cooler = next((d for d in devices if d.template.startswith("dc_external")), None)
    cx, cy = _CDU
    dx, dy = _DRY_COOLER
    px, py = _PUMP
    tx, ty = _TANK

    k.place(msp, ensure_cdu_block(doc), cx, cy)
    k.label(msp, cx, cy - 15, k.tag(cdu) if cdu else "CDU")
    k.place(msp, ensure_dry_cooler_block(doc), dx, dy)
    cooler_part = dtm.templates_used[cooler.template].equipment_id if cooler else None
    k.label(
        msp,
        dx,
        dy - 19,
        " ".join(filter(None, [k.tag(cooler) if cooler else None, cooler_part])),
    )
    k.label(msp, dx, dy - 23, "ARCNODE-SUPPLIED, ON CUSTOMER PAD", h=2.0)
    k.place(msp, ensure_pump_block(doc), px, py)
    k.label(msp, px, py - 10, "PUMP (BY OTHERS)", h=2.0)
    k.place(msp, ensure_buffer_tank_block(doc), tx, ty)

    # Supply (cold): dry cooler → pump → tank → CDU primary supply
    k.pipe(msp, (dx + 25, dy), (px - 6, py))
    k.pipe(msp, (px + 6, py), (tx - 15, ty))
    k.pipe(
        msp,
        (tx + 15, ty),
        (_SUPPLY_RISER_X, ty),
        (_SUPPLY_RISER_X, cy + 5),
        (cx - 19, cy + 5),
    )
    # Return (hot): CDU primary return → around the bottom → dry cooler inlet
    k.pipe(
        msp,
        (cx - 19, cy - 5),
        (_RETURN_DROP_X, cy - 5),
        (_RETURN_DROP_X, _RETURN_Y),
        (_RETURN_RISER_X, _RETURN_Y),
        (_RETURN_RISER_X, dy),
        (dx - 25, dy),
    )
    # Secondary side leaves the sheet to the rack loop
    k.pipe(msp, (cx + 19, cy + 5), (_OFFSHEET_X, cy + 5))
    k.offsheet(msp, doc, (_OFFSHEET_X, cy + 5), "TO SHEET 1", right=True, above=True)
    k.pipe(msp, (cx + 19, cy - 5), (_OFFSHEET_X, cy - 5))
    k.offsheet(msp, doc, (_OFFSHEET_X, cy - 5), "FROM SHEET 1", right=True, above=False)

    for tag, x in (("TT-201", 230), ("PT-202", 243)):
        k.instrument(msp, doc, tag, (x, ty + 14), (x, ty))
    for tag, x in (("TT-203", 200), ("PT-204", 213)):
        k.instrument(msp, doc, tag, (x, _RETURN_Y - 14), (x, _RETURN_Y))

    msp.add_line(
        (_WALL_X, 100),
        (_WALL_X, 262),
        dxfattribs={"layer": k.LAYER_BOUNDARY, "linetype": "DASHED"},
    )
    k.label(msp, _WALL_X + 3, 262, "COMPUTE CONTAINER >", h=2.5, left=True)
    k.label(msp, _WALL_X - 30, 262, "< CUSTOMER PAD", h=2.5)
    k.label(msp, _WALL_X + 3, 257, "CD PLATE AT THE WALL", h=2.0, left=True)
    k.label(
        msp,
        17,
        275,
        f"PRIMARY LOOP — ONE PER COMPUTE CONTAINER, C1-C{n} (TYPICAL OF {n})",
        h=2.5,
        left=True,
    )
    for i, note in enumerate(
        [
            "NOTES",
            "1. Primary loop per compute container: CDU, CD plate, dry cooler.",
            "2. Pump and buffer tank by others; dry cooler supplied by ARCNODE.",
            "3. Instrument tags per ISA 5.1.",
        ]
    ):
        k.label(msp, 15, 52 - i * 5, note, h=2.5 if i == 0 else 2.2, left=True)

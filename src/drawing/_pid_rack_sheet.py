"""P&ID sheet 1 — rack (secondary) coolant loop of compute container C1, typical.

CDU secondary supply feeds a supply header; each GPU node's DLC plate
branches off it and returns to a return header back to the CDU. The CDU's
primary ports run to off-sheet connectors (facility loop, sheet 2). Every
pipe ends on a port, a header or a connector.
"""

from typing import Final

from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from src.dtm.device_roles import GPU_NODE_TEMPLATES
from src.bom_generator.bom_ref_des import typical
from src.drawing import _pid_kit as k
from src.drawing._pid_symbols import ensure_cdu_block, ensure_dlc_plate_block
from src.shared.schemas.dtm import Dtm

_CDU: Final[tuple[float, float]] = (70.0, 190.0)
_SUPPLY_HDR_X: Final[float] = 140.0
_RETURN_HDR_X: Final[float] = 150.0
_PLATE_X: Final[float] = 230.0
_PLATE_TOP_Y: Final[float] = 240.0
_PLATE_PITCH: Final[float] = 22.0
_OFFSHEET_X: Final[float] = 36.0


def draw_rack_sheet(msp: Modelspace, doc: Drawing, dtm: Dtm) -> None:
    """Draw C1's rack loop, labelled typical of every compute container."""
    devices, n = k.typical_container(dtm)
    cdus = [d for d in devices if d.template == "cdu"]
    nodes = sorted(
        (d for d in devices if d.template in GPU_NODE_TEMPLATES),
        key=lambda d: int(d.device_id.rsplit("_", 1)[1]),
    )
    cx, cy = _CDU
    k.place(msp, ensure_cdu_block(doc), cx, cy)
    k.label(msp, cx, cy - 15, k.tag(cdus[0]) if cdus else "CDU")

    # Primary side leaves the sheet: supply in from, return out to, sheet 2
    k.pipe(msp, (cx - 19, cy + 5), (_OFFSHEET_X, cy + 5))
    k.offsheet(msp, doc, (_OFFSHEET_X, cy + 5), "FROM SHEET 2", right=False, above=True)
    k.pipe(msp, (cx - 19, cy - 5), (_OFFSHEET_X, cy - 5))
    k.offsheet(msp, doc, (_OFFSHEET_X, cy - 5), "TO SHEET 2", right=False, above=False)

    ys = [_PLATE_TOP_Y - i * _PLATE_PITCH for i in range(len(nodes))]
    supply_ys = [y + 3 for y in ys] + [cy + 5]
    return_ys = [y - 3 for y in ys] + [cy - 5]
    k.pipe(msp, (_SUPPLY_HDR_X, max(supply_ys)), (_SUPPLY_HDR_X, min(supply_ys)))
    k.pipe(msp, (_RETURN_HDR_X, max(return_ys)), (_RETURN_HDR_X, min(return_ys)))
    k.label(msp, _SUPPLY_HDR_X - 1, max(supply_ys) + 4, "SUPPLY HDR", h=1.8)
    k.label(msp, _RETURN_HDR_X + 1, min(return_ys) - 4, "RETURN HDR", h=1.8)
    # CDU secondary supply into the supply header; return header back to the CDU
    k.pipe(msp, (cx + 19, cy + 5), (_SUPPLY_HDR_X, cy + 5))
    k.pipe(msp, (cx + 19, cy - 5), (_RETURN_HDR_X, cy - 5))

    plate = ensure_dlc_plate_block(doc)
    for i, (node, y) in enumerate(zip(nodes, ys, strict=True)):
        k.place(msp, plate, _PLATE_X, y)
        k.label(msp, _PLATE_X, y + 8.5, f"{k.tag(node)} DLC", h=2.0)
        k.pipe(msp, (_SUPPLY_HDR_X, y + 3), (_PLATE_X - 14, y + 3))
        k.pipe(msp, (_PLATE_X - 14, y - 3), (_RETURN_HDR_X, y - 3))
        k.instrument(msp, doc, f"TT-{111 + i}", (_PLATE_X + 26, y), (_PLATE_X + 10, y))

    # Secondary supply: temperature, pressure, flow. Return: temperature, pressure.
    for tag, x in (("TT-101", 100), ("PT-102", 113), ("FT-103", 126)):
        k.instrument(msp, doc, tag, (x, cy + 19), (x, cy + 5))
    for tag, x in (("TT-104", 100), ("PT-105", 113)):
        k.instrument(msp, doc, tag, (x, cy - 19), (x, cy - 5))

    bottom = min([*ys, cy]) - 14
    msp.add_lwpolyline(
        [(15, bottom), (290, bottom), (290, 258), (15, 258)],
        close=True,
        dxfattribs={"layer": k.LAYER_BOUNDARY, "linetype": "DASHED"},
    )
    k.label(
        msp,
        17,
        bottom + 3,
        f"COMPUTE CONTAINER {typical('C', 1, n)} — RACK (SECONDARY) LOOP",
        h=2.5,
        left=True,
    )
    for i, note in enumerate(
        [
            "NOTES",
            "1. Secondary loop inside each compute container; primary loop on sheet 2.",
            "2. One DLC branch per GPU node; TT on every plate return.",
            "3. Instrument tags per ISA 5.1.",
        ]
    ):
        k.label(msp, 15, 52 - i * 5, note, h=2.5 if i == 0 else 2.2, left=True)

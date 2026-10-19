"""SLD sheet 2 — one compute container, typical of all of them.

Feeder in through CG → panelboard → one branch per PDU, CDU and dry
cooler. PDUs 1-3 form feed A, 4-6 feed B; every node PSU pair splits
across A and B (ADR-005: A/B dual-path from one source, not 2N).
"""

from ezdxf.layouts import Modelspace

from src.bom_generator.bom_models import Bom
from src.bom_generator.bom_ref_des import typical
from src.drawing import _draw_kit as k

_PANEL_BUS_Y: float = 245.0
_BRANCH_X0: float = 45.0
_BRANCH_PITCH: float = 45.0
_PDUS: int = 6


def draw_compute_sheet(msp: Modelspace, bom: Bom) -> None:
    """Draw the typical compute container one-line."""
    n = bom.compute_container_qty
    node = k.ordered(bom, "CMP-NODE-001", "CMP-NODE-002")
    cooler = k.ordered(bom, "EXT-DC-001", "EXT-DC-002")
    k.text(msp, 66, 278, "FROM GRID CONTAINER LV FEEDER (SHEET 1) VIA CG PLATE", h=2.2)
    k.wire(msp, (60, 280), (60, 257.5))
    k.breaker(msp, 60, 255)
    k.text(msp, 66, 255, "MAIN CMP-PNL-001", h=2.0)
    k.wire(msp, (60, 252.5), (60, _PANEL_BUS_Y))
    k.bus(msp, 30, 390, _PANEL_BUS_Y, "415Y/240 V PANELBOARD", 64)

    labels = [
        [f"PDU {i + 1} · FEED {'A' if i < 3 else 'B'}", "CMP-PDU-001"]
        for i in range(_PDUS)
    ]
    labels.append(["CDU", "CMP-CDU-001"])
    labels.append(["DRY COOLER", cooler])
    for i, lines in enumerate(labels):
        x = _BRANCH_X0 + i * _BRANCH_PITCH
        k.wire(msp, (x, _PANEL_BUS_Y), (x, 237.5))
        k.breaker(msp, x, 235)
        k.wire(msp, (x, 232.5), (x, 222))
        k.box(msp, x, 215, 38, 12, lines)

    _feed(msp, "FEED A", range(0, 3), 192)
    _feed(msp, "FEED B", range(3, 6), 182)
    k.box(
        msp,
        160,
        150,
        200,
        16,
        [
            f"7x GPU NODE {node} · PSUs SPLIT A/B",
            "DATA SWITCH CMP-SWITCH-001 + MGMT SWITCH CMP-SWITCH-003",
        ],
    )
    k.wire(msp, (120, 192), (120, 158))
    k.wire(msp, (200, 182), (200, 158))

    k.dashed_rect(msp, 22, 132, 400, 270)
    k.text(msp, 24, 135, f"COMPUTE CONTAINER {typical('C', 1, n)}", h=2.5)
    equipment = [
        "CMP-PNL-001",
        "CMP-PDU-001",
        "CMP-CDU-001",
        cooler,
        node,
        "CMP-SWITCH-001",
        "CMP-SWITCH-003",
    ]
    k.equipment_list(msp, bom, equipment, 15, 120)
    partial = k.partial_container_note(bom)
    for i, note in enumerate(
        [
            "NOTES",
            "1. A/B dual-path from one source, not 2N: both paths share one feeder (ADR-005).",
            *([f"2. {partial}."] if partial else []),
        ]
    ):
        k.text(msp, 15, 52 - i * 5, note, h=2.5 if i == 0 else 2.2)


def _feed(msp: Modelspace, label: str, pdus: range, y: float) -> None:
    """Bus joining a set of PDU outputs."""
    xs = [_BRANCH_X0 + i * _BRANCH_PITCH for i in pdus]
    for x in xs:
        k.wire(msp, (x, 208), (x, y))
    k.bus(msp, xs[0], xs[-1], y, label, xs[-1] + 3)

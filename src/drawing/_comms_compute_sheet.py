"""Comms sheet 2 — one compute container's management network, typical of all."""

from ezdxf.layouts import Modelspace

from src.bom_generator.bom_models import Bom
from src.drawing import _draw_kit as k
from src.drawing._comms_devices import device_lines, networked_children
from src.dtm.device_roles import COMPUTE_MODULE_TEMPLATES
from src.shared.schemas.dtm import Dtm

_PER_ROW: int = 8
_ROW_LAN_Y: tuple[float, float] = (225.0, 180.0)
_X0: float = 45.0
_PITCH: float = 46.5
_COOLER_NOTE: dict[str, list[str]] = {
    "EXT-DC-001": [
        "2. Dry cooler DC-1: Modbus TCP straight from its GMMnext controller (ETH1,",
        "   compatibility mode) over an outdoor Cat6 STP run; no converter.",
    ],
    "EXT-DC-002": [
        "2. Dry cooler DC-1 is not networked: no verified register map for its",
        "   controller yet.",
    ],
}


def draw_compute_sheet(msp: Modelspace, dtm: Dtm, bom: Bom) -> None:
    """Draw C1's devices behind its management switch."""
    n = bom.compute_container_qty
    cooler = k.ordered(bom, "EXT-DC-001", "EXT-DC-002")
    k.box(msp, 210, 272, 80, 9, ["TO GRID CONTAINER MGMT SWITCH (SHEET 1) VIA CG"])
    k.wire(msp, (210, 267.5), (210, 252))
    k.box(msp, 210, 246, 60, 11, ["MGMT SWITCH CMP-SWITCH-003", "1 GbE"])
    k.wire(msp, (210, 240.5), (210, _ROW_LAN_Y[0]))

    devices = sorted(
        networked_children(dtm, _first_compute_module(dtm)), key=lambda d: d.device_id
    )
    rows = [devices[:_PER_ROW], devices[_PER_ROW:]]
    # Reason: one trunk on the left joins both row LANs to the switch drop.
    k.wire(msp, (18, _ROW_LAN_Y[0]), (18, _ROW_LAN_Y[1]))
    for lan_y, row in zip(_ROW_LAN_Y, rows, strict=True):
        if not row:
            continue
        xs = [_X0 + i * _PITCH for i in range(len(row))]
        k.wire(msp, (18, lan_y), (max(xs[-1], 210), lan_y))
        for x, device in zip(xs, row, strict=True):
            k.wire(msp, (x, lan_y), (x, lan_y - 10))
            k.box(msp, x, lan_y - 17, 42, 13, device_lines(dtm, device))

    k.dashed_rect(msp, 12, 140, 405, 262)
    k.text(msp, 14, 143, f"COMPUTE CONTAINER C1-C{n} (TYPICAL OF {n})", h=2.5)
    equipment = [
        "CMP-SWITCH-003",
        k.ordered(bom, "CMP-NODE-001", "CMP-NODE-002"),
        "CMP-PDU-001",
        "CMP-CDU-001",
        "CMP-SWITCH-001",
    ]
    k.equipment_list(msp, bom, equipment, 15, 128)
    for i, note in enumerate(
        [
            "NOTES",
            "1. Server BMCs, PDUs, CDU and the SN5600 management port share the 1 GbE",
            "   management switch; the SN5600 data plane is not drawn (ADR-019).",
            *_COOLER_NOTE[cooler],
        ]
    ):
        k.text(msp, 15, 62 - i * 5, note, h=2.5 if i == 0 else 2.2)


def _first_compute_module(dtm: Dtm) -> str:
    """C1's device id, whichever compute module template the order uses.

    DTM module ids are <template>_<n>, so the lowest n is C1.
    """
    modules = [
        d.device_id
        for d in dtm.devices.values()
        if d.parent is None and d.template in COMPUTE_MODULE_TEMPLATES
    ]
    return min(modules, key=lambda m: int(m.rsplit("_", 1)[1]))

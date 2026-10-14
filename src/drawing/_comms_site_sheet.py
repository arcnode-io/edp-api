"""Comms sheet 1 — site management network (ADR-019).

EMS gateway → G1 management switch → G1's networked devices, the
customer's BESS controller, the G2-GM switches (typical) and one uplink
per compute container (detail on sheet 2).
"""

from ezdxf.layouts import Modelspace

from src.bom_generator.bom_models import Bom
from src.drawing import _draw_kit as k
from src.drawing._comms_devices import device_lines, networked_children
from src.shared.schemas.dtm import Dtm

_LAN_Y: float = 215.0
_DROP_X0: float = 45.0
_DROP_PITCH: float = 70.0


def draw_site_sheet(msp: Modelspace, dtm: Dtm, bom: Bom) -> None:
    """Draw the site management network."""
    n, m = bom.compute_container_qty, bom.grid_container_qty
    k.box(msp, 210, 265, 70, 11, ["EMS GATEWAY", "PLATFORM-EMS-ISO HOST — BY OTHERS"])
    k.wire(msp, (210, 259.5), (210, 241))
    k.box(msp, 210, 235, 60, 11, ["MGMT SWITCH GRD-SWITCH-001", "GRID CONTAINER G1"])
    k.wire(msp, (210, 229.5), (210, _LAN_Y))

    boxes = [device_lines(dtm, d) for d in networked_children(dtm, "grid_module_1")]
    # The customer's battery, from the device data (BESS-1)
    modules = [d.device_id for d in dtm.devices.values() if d.template == "bess_module"]
    boxes += [device_lines(dtm, d) for d in dtm.devices.values() if d.parent in modules]
    if m > 1:
        boxes.append(
            [f"G2-G{m} MGMT SWITCHES x{m - 1}", "RELAY BEHIND EACH", "TYPICAL"]
        )
    boxes.append([f"C1-C{n} MGMT SWITCH UPLINKS x{n}", "VIA CG PLATE", "SHEET 2"])

    xs = [_DROP_X0 + i * _DROP_PITCH for i in range(len(boxes))]
    k.wire(msp, (xs[0], _LAN_Y), (xs[-1], _LAN_Y))
    for x, lines in zip(xs, boxes, strict=True):
        k.wire(msp, (x, _LAN_Y), (x, 203))
        k.box(msp, x, 196, 46, 13, lines)

    k.equipment_list(msp, bom, ["GRD-SWITCH-001"], 15, 120)
    for i, note in enumerate(
        [
            "NOTES",
            "1. 1 GbE management network, one managed switch per container (ADR-019).",
            "2. Addresses are assigned at commissioning (POST /topology).",
            "3. PART TBD: selection + fit pending (ADR-019).",
        ]
    ):
        k.text(msp, 15, 52 - i * 5, note, h=2.5 if i == 0 else 2.2)

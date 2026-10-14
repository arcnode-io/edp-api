"""P&ID drawing helpers shared by the rack and facility sheets (mm, y up)."""

from itertools import pairwise
from typing import Final

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from src.drawing._pid_symbols import ensure_instrument_bubble, ensure_offsheet_block
from src.shared.schemas.dtm import Device, Dtm

LAYER_PROCESS: Final[str] = "PROCESS"  # pipes + equipment outlines
LAYER_INSTR: Final[str] = "INSTRUMENT"  # bubbles + leader lines
LAYER_LABELS: Final[str] = "LABELS"
LAYER_BOUNDARY: Final[str] = "BOUNDARY"  # container wall / scope lines
LAYERS: Final[tuple[str, ...]] = (
    LAYER_PROCESS,
    LAYER_INSTR,
    LAYER_LABELS,
    LAYER_BOUNDARY,
    "FRAME",
    "TITLE_BLOCK",
)


def pipe(msp: Modelspace, *points: tuple[float, float]) -> None:
    """Process pipe through the points, one LINE per straight run."""
    for a, b in pairwise(points):
        msp.add_line(a, b, dxfattribs={"layer": LAYER_PROCESS})


def place(msp: Modelspace, block: str, x: float, y: float, rotation: float = 0) -> None:
    """INSERT a process symbol."""
    msp.add_blockref(
        block, (x, y), dxfattribs={"layer": LAYER_PROCESS, "rotation": rotation}
    )


def label(
    msp: Modelspace, x: float, y: float, text: str, h: float = 2.2, left: bool = False
) -> None:
    """Single-line label, centered (or left-aligned) on (x, y)."""
    align = (
        TextEntityAlignment.MIDDLE_LEFT if left else TextEntityAlignment.MIDDLE_CENTER
    )
    msp.add_text(text, dxfattribs={"layer": LAYER_LABELS, "height": h}).set_placement(
        (x, y), align=align
    )


def instrument(
    msp: Modelspace,
    doc: Drawing,
    tag: str,
    bubble: tuple[float, float],
    tap: tuple[float, float],
) -> None:
    """ISA 5.1 bubble with a dashed leader to its tap point on a pipe."""
    msp.add_blockref(
        ensure_instrument_bubble(doc, tag), bubble, dxfattribs={"layer": LAYER_INSTR}
    )
    # Reason: the leader stops at the bubble's edge (radius 5), not its centre.
    bx, by = bubble
    tx, ty = tap
    dist = ((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5
    edge = (bx + (tx - bx) * 5 / dist, by + (ty - by) * 5 / dist)
    msp.add_line(edge, tap, dxfattribs={"layer": LAYER_INSTR, "linetype": "DASHED"})


def offsheet(
    msp: Modelspace,
    doc: Drawing,
    at: tuple[float, float],
    text: str,
    *,
    right: bool,
    above: bool,
) -> None:
    """Off-sheet connector whose flat end sits on `at`; label above or below."""
    place(msp, ensure_offsheet_block(doc), at[0], at[1], 180 if right else 0)
    mid = at[0] + (7.5 if right else -7.5)
    label(msp, mid, at[1] + (5.5 if above else -5.5), text, h=2.0)


def typical_container(dtm: Dtm) -> tuple[list[Device], int]:
    """(devices in compute container 1, number of compute containers).

    Every compute container is identical, so the P&ID draws C1 as typical.
    """
    modules = sorted(
        (d for d in dtm.devices.values() if d.template == "compute_module"),
        key=lambda d: int(d.device_id.rsplit("_", 1)[1]),
    )
    first = modules[0].device_id if modules else None
    children = [d for d in dtm.devices.values() if d.parent == first]
    return children, len(modules)


def tag(device: Device) -> str:
    """Site tag (C1-CDU-1), or the device id where the DTM carries none."""
    return device.display_name or device.device_id

"""Modelspace primitives for the engineering SLD + comms sheets (mm, y up).

Symbols follow IEC 60617 / ANSI one-line conventions and are drawn on a
vertical conductor through (x, y):
- breaker: square (ANSI 52 / IEC drawout breaker box)
- disconnect: open blade
- transformer: two overlapping circles (two-winding)
- source: circle with "~"
- meter: CT ring on the conductor + "M" bubble off to the side
"""

from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from src.bom_generator.bom_models import Bom

LAYER_GEAR: str = "GEAR"
LAYER_WIRE: str = "WIRE"
LAYER_TEXT: str = "TEXT"
LAYERS: tuple[str, ...] = (LAYER_GEAR, LAYER_WIRE, LAYER_TEXT, "FRAME", "TITLE_BLOCK")

_BUS_WIDTH: float = 0.8
# Rendered width of one 2.2 mm character (measured on the PDF output).
_CHAR_W: float = 2.0


def text(msp: Modelspace, x: float, y: float, s: str, h: float = 2.2) -> None:
    """Left-aligned single line, vertically centered on y."""
    msp.add_text(s, dxfattribs={"layer": LAYER_TEXT, "height": h}).set_placement(
        (x, y), align=TextEntityAlignment.MIDDLE_LEFT
    )


def ctext(msp: Modelspace, x: float, y: float, s: str, h: float = 2.2) -> None:
    """Centered single line."""
    msp.add_text(s, dxfattribs={"layer": LAYER_TEXT, "height": h}).set_placement(
        (x, y), align=TextEntityAlignment.MIDDLE_CENTER
    )


def wire(msp: Modelspace, *points: tuple[float, float]) -> None:
    """Conductor polyline through the given points."""
    msp.add_lwpolyline(list(points), dxfattribs={"layer": LAYER_WIRE})


def bus(
    msp: Modelspace, x0: float, x1: float, y: float, label: str, label_x: float
) -> None:
    """Bold horizontal bus bar, label above it from label_x (clear of wires)."""
    msp.add_lwpolyline(
        [(x0, y), (x1, y)],
        dxfattribs={"layer": LAYER_WIRE, "const_width": _BUS_WIDTH},
    )
    text(msp, label_x, y + 3, label, h=2.5)


def breaker(msp: Modelspace, x: float, y: float) -> None:
    """5 mm square on the conductor."""
    _rect(msp, x - 2.5, y - 2.5, x + 2.5, y + 2.5)


def disconnect(msp: Modelspace, x: float, y: float) -> None:
    """Open blade between y-3 and y+3."""
    msp.add_line((x, y - 3), (x + 3, y + 2.5), dxfattribs={"layer": LAYER_GEAR})
    msp.add_circle((x, y - 3), 0.5, dxfattribs={"layer": LAYER_GEAR})


def transformer(msp: Modelspace, x: float, y: float) -> None:
    """Two-winding transformer, 10 mm tall, centered on y."""
    msp.add_circle((x, y + 2.5), 4, dxfattribs={"layer": LAYER_GEAR})
    msp.add_circle((x, y - 2.5), 4, dxfattribs={"layer": LAYER_GEAR})


def source(msp: Modelspace, x: float, y: float) -> None:
    """AC source / utility: circle with a tilde."""
    msp.add_circle((x, y), 5, dxfattribs={"layer": LAYER_GEAR})
    ctext(msp, x, y, "~", h=4)


def meter(msp: Modelspace, x: float, y: float) -> None:
    """CT ring on the conductor, dashed tap to an M bubble on the right."""
    msp.add_circle((x, y), 1.8, dxfattribs={"layer": LAYER_GEAR})
    msp.add_line(
        (x + 1.8, y), (x + 8, y), dxfattribs={"layer": LAYER_GEAR, "linetype": "DASHED"}
    )
    msp.add_circle((x + 11, y), 3, dxfattribs={"layer": LAYER_GEAR})
    ctext(msp, x + 11, y, "M", h=2.5)


def box(
    msp: Modelspace, x: float, y: float, w: float, h: float, lines: list[str]
) -> None:
    """Rectangle centered on (x, y) with centered lines; widens to fit text."""
    w = max(w, max(len(line) for line in lines) * _CHAR_W + 4)
    _rect(msp, x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    pitch = 3.2
    top = y + (len(lines) - 1) * pitch / 2
    for i, line in enumerate(lines):
        ctext(msp, x, top - i * pitch, line, h=2.2)


def dashed_rect(msp: Modelspace, x0: float, y0: float, x1: float, y1: float) -> None:
    """Dashed enclosure — a container or a by-others boundary."""
    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        close=True,
        dxfattribs={"layer": LAYER_GEAR, "linetype": "DASHED"},
    )


def model(bom: Bom, equipment_id: str) -> str:
    """Short model from the BOM, or PART TBD when it isn't specified yet."""
    line = next((li for li in bom.line_items if li.equipment_id == equipment_id), None)
    if line is None:
        return "PART TBD"
    # Reason: model numbers carry a long "(...)" spec tail; the sheet wants
    # the short model, the BOM has the rest.
    return f"{line.vendor} {line.part_number.split(' (')[0]}"[:70]


def part(bom: Bom, equipment_id: str) -> str:
    """'<id> <short model>' — the equipment list's row text."""
    return f"{equipment_id} {model(bom, equipment_id)}"


def equipment_list(
    msp: Modelspace, bom: Bom, ids: list[str], x: float, y: float
) -> None:
    """Table of every equipment id on the sheet → its model (or PART TBD)."""
    text(msp, x, y, "EQUIPMENT", h=2.5)
    for i, eid in enumerate(ids, start=1):
        text(msp, x, y - i * 4, eid, h=2.2)
        text(msp, x + 30, y - i * 4, model(bom, eid), h=2.2)


def _rect(msp: Modelspace, x0: float, y0: float, x1: float, y1: float) -> None:
    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        close=True,
        dxfattribs={"layer": LAYER_GEAR},
    )

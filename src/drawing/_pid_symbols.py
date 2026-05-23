"""ISA 5.1 / ANSI 5.5 graphical symbols for the cooling P&ID.

Each `ensure_*_block` function defines an ezdxf block once per document
(idempotent — same block name returns the existing block). The caller
INSERTs at the appropriate position + scale.

Block taxonomy (block-name prefix → category):
- `equip_*`  — process equipment (CDU, manifold, DLC plate, dry cooler,
               buffer tank, heat exchanger).
- `instr_*`  — ISA 5.1 instrument bubbles (TT/PT/FT/LT with field tag).
- `valve_*`  — ISA 5.1 valve glyphs (gate, check).
- `pump_*`   — ISA 5.1 pump glyph (centrifugal, circle + triangle).
- `byother_*`— BY-OTHERS placeholder (dashed rectangle + label) for
               customer-supplied gear on the facility loop sheet.

Geometry conventions (mm at paper scale):
- Equipment dominant size: 30x20 mm rectangle.
- Instrument bubble: Ø10 mm circle, two-line text inside.
- Valve bowtie: 8 mm wide, 8 mm tall.
- Pump: Ø12 mm circle with inscribed triangle.
- BY-OTHERS placeholder: 50x30 mm dashed rectangle with centered label.
"""

from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout


def ensure_cdu_block(doc: Drawing) -> str:
    """30x20 mm rectangle labelled 'CDU'. Four port stubs (PRI_S/R, SEC_S/R)."""
    name = "equip_cdu"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    _equipment_rectangle(blk, w=30, h=20, label="CDU")
    # Port stubs — 4mm pegs at midpoints of each side.
    blk.add_line(start=(-15, 5), end=(-19, 5))  # PRI supply (left top)
    blk.add_line(start=(-15, -5), end=(-19, -5))  # PRI return (left bottom)
    blk.add_line(start=(15, 5), end=(19, 5))  # SEC supply (right top)
    blk.add_line(start=(15, -5), end=(19, -5))  # SEC return (right bottom)
    return name


def ensure_dlc_plate_block(doc: Drawing) -> str:
    """20x12 mm rectangle labelled 'DLC'. Two ports (supply + return)."""
    name = "equip_dlc_plate"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    _equipment_rectangle(blk, w=20, h=12, label="DLC")
    blk.add_line(start=(-10, 3), end=(-14, 3))  # supply
    blk.add_line(start=(-10, -3), end=(-14, -3))  # return
    return name


def ensure_manifold_block(doc: Drawing) -> str:
    """Vertical manifold — 4x60 mm bar. Caller positions/scales tee branches."""
    name = "equip_manifold"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    # Filled-ish rectangle as a bus header (4mm wide, 60mm tall).
    blk.add_lwpolyline(
        [(-2, -30), (2, -30), (2, 30), (-2, 30)],
        close=True,
    )
    return name


def ensure_dry_cooler_block(doc: Drawing) -> str:
    """50x30 mm BY-OTHERS placeholder labelled 'DRY COOLER (BY OTHERS)'."""
    return ensure_by_others_block(doc, "dry_cooler", "DRY COOLER (BY OTHERS)")


def ensure_buffer_tank_block(doc: Drawing) -> str:
    """30x40 mm BY-OTHERS placeholder labelled 'BUFFER TANK (BY OTHERS)'."""
    name = "byother_buffer_tank"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    _dashed_rectangle(blk, w=30, h=40)
    blk.add_text(
        "BUFFER TANK",
        dxfattribs={"height": 2.5, "halign": 4, "valign": 2, "align_point": (0, 4)},
    )
    blk.add_text(
        "(BY OTHERS)",
        dxfattribs={"height": 2.0, "halign": 4, "valign": 2, "align_point": (0, 0)},
    )
    return name


def ensure_pump_block(doc: Drawing) -> str:
    """ISA 5.1 centrifugal pump — Ø12mm circle with inscribed triangle.

    BY OTHERS variant: caller adds the 'BY OTHERS' label as a sibling text
    annotation since some pumps in the P&ID may be ARCNODE-supplied later.
    """
    name = "pump_centrifugal"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    blk.add_circle(center=(0, 0), radius=6)
    # Triangle apex at top, base at bottom — ISA standard impeller indicator.
    blk.add_lwpolyline([(-4, -3), (4, -3), (0, 4)], close=True)
    return name


def ensure_gate_valve_block(doc: Drawing) -> str:
    """ISA 5.1 manual gate valve — bowtie 8mm wide, 8mm tall."""
    name = "valve_gate"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    # Two triangles meeting at center: left-pointing and right-pointing.
    blk.add_lwpolyline([(-4, 4), (-4, -4), (0, 0)], close=True)
    blk.add_lwpolyline([(4, 4), (4, -4), (0, 0)], close=True)
    return name


def ensure_check_valve_block(doc: Drawing) -> str:
    """ISA 5.1 check valve — bowtie with directional arrow inside."""
    name = "valve_check"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    blk.add_lwpolyline([(-4, 4), (-4, -4), (0, 0)], close=True)
    blk.add_lwpolyline([(4, 4), (4, -4), (0, 0)], close=True)
    # Arrow head (->) inside the right triangle.
    blk.add_line(start=(1, 2), end=(3, 0))
    blk.add_line(start=(1, -2), end=(3, 0))
    return name


def ensure_instrument_bubble(doc: Drawing, tag: str) -> str:
    """ISA 5.1 instrument bubble — Ø10 mm circle + 2-letter ID over tag number.

    `tag` follows ISA 5.1 convention: 2-letter measurement+function code on
    top row (TT, PT, FT, LT, TC, TI, ...), tag number on bottom row.
    Returns a per-tag block name so each bubble is uniquely INSERTed.
    """
    name = f"instr_{tag.lower().replace('-', '_')}"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    blk.add_circle(center=(0, 0), radius=5)
    # Horizontal divider inside the bubble.
    blk.add_line(start=(-5, 0), end=(5, 0))
    # 2 lines of text: tag prefix on top, tag number on bottom.
    prefix, _, number = tag.partition("-")
    blk.add_text(
        prefix,
        dxfattribs={
            "height": 2.2,
            "halign": 4,
            "valign": 2,
            "align_point": (0, 1.8),
        },
    )
    blk.add_text(
        number,
        dxfattribs={
            "height": 2.0,
            "halign": 4,
            "valign": 2,
            "align_point": (0, -1.8),
        },
    )
    return name


def ensure_by_others_block(doc: Drawing, kind: str, label: str) -> str:
    """Generic BY-OTHERS placeholder — dashed rectangle + centered label."""
    name = f"byother_{kind}"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    _dashed_rectangle(blk, w=50, h=30)
    blk.add_text(
        label,
        dxfattribs={
            "height": 2.5,
            "halign": 4,
            "valign": 2,
            "align_point": (0, 0),
        },
    )
    return name


def _equipment_rectangle(blk: BlockLayout, *, w: float, h: float, label: str) -> None:
    """Solid rectangle of given size with centered text label."""
    hw, hh = w / 2, h / 2
    blk.add_lwpolyline([(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)], close=True)
    blk.add_text(
        label,
        dxfattribs={
            "height": 3.5,
            "halign": 4,
            "valign": 2,
            "align_point": (0, 0),
        },
    )


def _dashed_rectangle(blk: BlockLayout, *, w: float, h: float) -> None:
    """Outlined rectangle with a dashed linetype to mark BY-OTHERS scope.

    Linetype 'DASHED' is in the ezdxf default linetype set when the doc was
    created with `setup=True`. Lines on this block are explicitly tagged so
    the BY-OTHERS visual distinction holds in DXF + PDF rendering alike.
    """
    hw, hh = w / 2, h / 2
    pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    for i in range(len(pts) - 1):
        blk.add_line(
            start=pts[i],
            end=pts[i + 1],
            dxfattribs={"linetype": "DASHED"},
        )

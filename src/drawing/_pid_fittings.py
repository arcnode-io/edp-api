"""ISA 5.1 pump, valve and instrument-bubble blocks for the cooling P&ID.

Split out of _pid_symbols.py (200-line budget); same idempotent
`ensure_*_block` convention.
- `pump_*`  — centrifugal pump, Ø12 mm circle with inscribed triangle.
- `valve_*` — gate and check valve bowties, 8 x 8 mm.
- `instr_*` — Ø10 mm instrument bubble, two-line text inside.
"""

from ezdxf.document import Drawing


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

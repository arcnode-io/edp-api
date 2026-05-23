"""Network-topology symbols for the comms diagram.

IEEE-802 style device boxes with role-specific glyphs:
- `device_box`     — generic endpoint (40x16mm rect with 2 text rows).
- `switch_glyph`   — Ethernet switch (3-rectangle stack with arrows).
- `gateway_glyph`  — gateway/aggregation point (rounded rect labelled GW).

All blocks are coordinate-origin-centered. Caller INSERTs at the
destination point; ezdxf does translation.
"""

from ezdxf.document import Drawing


def ensure_device_box_block(doc: Drawing) -> str:
    """40x16 mm rectangle. Caller adds device_id + host:port labels as TEXT."""
    name = "comms_device_box"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    blk.add_lwpolyline([(-20, -8), (20, -8), (20, 8), (-20, 8)], close=True)
    return name


def ensure_switch_glyph_block(doc: Drawing) -> str:
    """Ethernet switch — stack of 3 thin rectangles (IEEE-style)."""
    name = "comms_switch_glyph"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    # 3 stacked horizontal bars 16mm wide, 3mm tall each, 1mm gap.
    for i in range(3):
        y = -4 + i * 4
        blk.add_lwpolyline([(-8, y), (8, y), (8, y + 3), (-8, y + 3)], close=True)
    return name


def ensure_gateway_glyph_block(doc: Drawing) -> str:
    """Gateway / aggregation point — 24x14mm rounded-corner box (approx) + GW label."""
    name = "comms_gateway_glyph"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    # Pseudo-rounded corners: octagon-like outline.
    blk.add_lwpolyline(
        [
            (-12, -5),
            (-10, -7),
            (10, -7),
            (12, -5),
            (12, 5),
            (10, 7),
            (-10, 7),
            (-12, 5),
        ],
        close=True,
    )
    blk.add_text(
        "GW",
        dxfattribs={
            "height": 4.0,
            "halign": 4,
            "valign": 2,
            "align_point": (0, 0),
        },
    )
    return name

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
    """ARCNODE Industrial Gateway — 36x14mm rounded-corner box + GATEWAY label.

    Bridges south-side device protocols (Modbus / DNP3 / SNMP / Redfish /
    CANopen) up to MQTT. One per protocol cluster on the diagram.
    """
    name = "comms_gateway_glyph"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    # Pseudo-rounded corners: octagon-like outline. Wider than the v1 GW
    # box so the full "GATEWAY" label fits without crowding.
    blk.add_lwpolyline(
        [
            (-18, -5),
            (-16, -7),
            (16, -7),
            (18, -5),
            (18, 5),
            (16, 7),
            (-16, 7),
            (-18, 5),
        ],
        close=True,
    )
    blk.add_text(
        "GATEWAY",
        dxfattribs={
            "height": 3.5,
            "halign": 4,
            "valign": 2,
            "align_point": (0, 0),
        },
    )
    return name

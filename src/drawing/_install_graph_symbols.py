"""Symbols for the schematic installation graph — labeled boxes + clearance halos.

Single equipment block (labeled rectangle) reused across all device
templates — install graph doesn't differentiate by symbol like SLD
does. Clearance halo is a separate dashed rectangle drawn around each
equipment instance.
"""

from ezdxf.document import Drawing

from src.drawing._install_graph_layout import (
    CLEARANCE_H,
    CLEARANCE_W,
    EQUIPMENT_H,
    EQUIPMENT_W,
)


def ensure_equipment_box_block(doc: Drawing) -> str:
    """24x16mm labeled rectangle. Caller adds the device_id text annotation."""
    name = "install_equipment_box"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    hw, hh = EQUIPMENT_W / 2, EQUIPMENT_H / 2
    blk.add_lwpolyline([(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)], close=True)
    return name


def ensure_clearance_halo_block(doc: Drawing) -> str:
    """Dashed rectangle 4mm larger per side — visual service-clearance reminder."""
    name = "install_clearance_halo"
    if name in doc.blocks:
        return name
    blk = doc.blocks.new(name=name)
    hw, hh = CLEARANCE_W / 2, CLEARANCE_H / 2
    pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    for i in range(len(pts) - 1):
        blk.add_line(start=pts[i], end=pts[i + 1], dxfattribs={"linetype": "DASHED"})
    return name

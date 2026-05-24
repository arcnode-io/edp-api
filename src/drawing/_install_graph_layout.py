"""Schematic layout for the installation graph — per-module floor plan.

v1 is SCHEMATIC, NOT to scale. Equipment positions are derived from
template slug + arrangement convention (rack stack along one wall,
ancillary equipment on opposite wall). Precise layout coordinates
land in v2 when edp-module-assemblies surfaces a layout.json artifact
alongside each assembly's topology.yaml.

Coordinate convention (mm at paper scale, NOT real container scale):
- Container outline: 200x140mm rectangle representing the floor of a
  10ft high-cube ISO (real interior 2680x2235x2591 mm — see ADR-004).
- Equipment boxes: ~24x16mm rectangles, labeled with device_id.
- Service-clearance halos: ~30x22mm dashed boxes around each device.
- Compute module convention: rack stack along left wall, CDU at top of
  stack, network switch above CDU, PDUs flanking rack at corners.
- Grid module convention: equipment row along left wall (transformer →
  switchgear → meter → relay → PCS, in physical-current order).
"""

from dataclasses import dataclass

# Container outline (paper-mm at A3 landscape scale).
CONTAINER_X: float = 100.0
CONTAINER_Y: float = 80.0
CONTAINER_WIDTH: float = 200.0
CONTAINER_HEIGHT: float = 140.0

# Equipment box + clearance halo footprint.
EQUIPMENT_W: float = 24.0
EQUIPMENT_H: float = 16.0
CLEARANCE_W: float = 32.0  # 4mm halo each side
CLEARANCE_H: float = 24.0  # 4mm halo top/bottom

# Schematic stack-pitch — vertical spacing between equipment along a wall.
STACK_PITCH_Y: float = 26.0

# Where the first equipment slot lives along the rack-stack wall.
RACK_WALL_X: float = CONTAINER_X + 20.0
RACK_WALL_Y_TOP: float = CONTAINER_Y + CONTAINER_HEIGHT - 25.0


@dataclass(frozen=True)
class Placement:
    """One device's schematic position within the container outline."""

    device_id: str
    x: float
    y: float


def stack_devices_along_wall(device_ids: list[str]) -> list[Placement]:
    """Top-down rack-stack layout along the left wall.

    Devices placed top-to-bottom from `RACK_WALL_Y_TOP`. Overflow wraps
    to a second column once we run out of vertical room — v1 doesn't
    paginate cleanly past ~5 devices per module, that limit is documented
    in the service docstring.
    """
    placements: list[Placement] = []
    for i, did in enumerate(device_ids):
        col = i // 5  # second column kicks in after the 5th device
        row = i % 5
        x = RACK_WALL_X + col * 50.0
        y = RACK_WALL_Y_TOP - row * STACK_PITCH_Y
        placements.append(Placement(device_id=did, x=x, y=y))
    return placements

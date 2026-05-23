"""P&ID sheet layout — coordinates for the rack-internal + facility-loop sheets.

Sheet origin (0,0) at bottom-left; A3 landscape modelspace 420x297 mm.
Title block occupies the lower-right corner (per `_eng_title_block`), so
the usable P&ID canvas is roughly 360x230 mm above + left of it.

Layout rule (v1, rack-internal sheet):
- CDU on the left (~50, ~180), 30x20mm.
- Vertical manifold to the right of the CDU (~110, ~180), 4x60mm.
- N DLC plates stacked vertically right of the manifold, each 20x12mm.
- Instrument bubbles arranged around CDU ports + manifold + plate returns.

Layout rule (v1, facility-loop sheet):
- BY-OTHERS dry cooler in upper-left.
- BY-OTHERS pump + buffer tank in middle.
- CDU mirror on the right (same symbol as sheet 1 for continuity).
- Dashed boundary line down the page between BY-OTHERS gear and CDU.
"""

from dataclasses import dataclass

# Sheet-1 layout anchors (mm). Conservative — leave room for instrument
# bubbles + tag annotations. Title block at lower-right consumes the
# bottom-right 200x50mm region.
SHEET1_CDU_X: float = 60.0
SHEET1_CDU_Y: float = 180.0

SHEET1_MANIFOLD_X: float = 130.0
SHEET1_MANIFOLD_Y: float = 180.0

SHEET1_PLATE_X: float = 200.0
# Top plate y aligned with manifold top (180 + 30 = 210); manifold-stretching
# for >5 plates is a v2 concern (`stack_dlc_plates` currently doesn't grow
# the manifold). v1 covers up to ~5 plates per CDU at 25mm pitch.
SHEET1_PLATE_Y_TOP: float = 210.0
SHEET1_PLATE_Y_PITCH: float = 25.0  # vertical spacing between stacked plates


# Sheet-2 layout anchors (mm).
SHEET2_DRY_COOLER_X: float = 60.0
SHEET2_DRY_COOLER_Y: float = 230.0

SHEET2_PUMP_X: float = 60.0
SHEET2_PUMP_Y: float = 150.0

SHEET2_BUFFER_TANK_X: float = 160.0
SHEET2_BUFFER_TANK_Y: float = 150.0

SHEET2_CDU_X: float = 280.0
SHEET2_CDU_Y: float = 180.0

# Vertical boundary line between BY-OTHERS gear and the CDU. Drawn as
# a dashed line down the full sheet height; instrument bubbles to the
# left of this line are BY OTHERS.
SHEET2_BOUNDARY_X: float = 230.0


@dataclass(frozen=True)
class Placement:
    """One symbol's position on a sheet."""

    insert_x: float
    insert_y: float


def stack_dlc_plates(plate_count: int) -> list[Placement]:
    """Return one Placement per DLC plate, stacked vertically right of manifold."""
    placements: list[Placement] = []
    for i in range(plate_count):
        y = SHEET1_PLATE_Y_TOP - i * SHEET1_PLATE_Y_PITCH
        placements.append(Placement(insert_x=SHEET1_PLATE_X, insert_y=y))
    return placements

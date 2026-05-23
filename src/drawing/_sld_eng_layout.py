"""Grid layout for the engineering SLD.

Deterministic placement on the A3 sheet (420x297 mm modelspace). Title
block occupies the bottom-right corner (~180x40 mm); the SLD drawing
area is the remaining ~360x220 mm canvas above it.

Layout rule (v1): one row per bus, devices spaced along the row in
bus.members order. Devices that don't belong to any bus stack into an
"unattached" row at the top. Bus rows ordered by appearance.

Source-side rule: same as the HMI SVG — first member of bus.members
whose template carries MMXU.W is the source. Renders left of the others
to preserve "source flows right" reading convention in latin scripts.

Coordinates are in mm. Sheet origin (0,0) = bottom-left corner per the
ISO 5457 convention for engineering drawing sheets.
"""

from dataclasses import dataclass

from src.drawing._iec_61850 import source_member_index
from src.shared.schemas.dtm import Bus, Dtm

# Drawing area: leaves 30 mm margins all around, and 50 mm at the bottom
# for the title block (which itself spans ~180mm in the right corner).
_DRAW_LEFT: float = 30.0
_DRAW_RIGHT: float = 390.0
_DRAW_TOP: float = 267.0  # 297 - 30 margin
_DRAW_BOTTOM_ROWS: float = 65.0  # leave 65mm at the bottom for title block + frame

_DEVICE_X_PITCH: float = 50.0  # horizontal spacing between devices on a bus
_ROW_Y_PITCH: float = 35.0  # vertical spacing between bus rows


@dataclass(frozen=True)
class DevicePlacement:
    """One device's position on the sheet."""

    device_id: str
    x: float
    y: float


def layout_devices(dtm: Dtm) -> dict[str, DevicePlacement]:
    """Return device_id -> placement, deterministic per DTM.

    Devices on buses come first (one row per bus). Devices not attached to
    any bus stack into an extra row at the top — they still get drawn so
    nothing is silently dropped from review.
    """
    placements: dict[str, DevicePlacement] = {}
    used: set[str] = set()

    # Top of drawing area starts at _DRAW_TOP; each row consumes _ROW_Y_PITCH.
    y_cursor = _DRAW_TOP

    # Unattached row first (if any). Devices with no bus parent.
    on_bus = {m.device_id for bus in dtm.buses for m in bus.members}
    unattached = [did for did in dtm.devices if did not in on_bus]
    if unattached:
        for i, did in enumerate(sorted(unattached)):
            placements[did] = DevicePlacement(
                device_id=did, x=_DRAW_LEFT + i * _DEVICE_X_PITCH, y=y_cursor
            )
            used.add(did)
        y_cursor -= _ROW_Y_PITCH

    # One row per bus. Members ordered source-first.
    for bus in dtm.buses:
        ordered = _bus_members_source_first(bus, dtm)
        for i, member_id in enumerate(ordered):
            if member_id in used:
                continue  # already placed (multi-bus device)
            placements[member_id] = DevicePlacement(
                device_id=member_id, x=_DRAW_LEFT + i * _DEVICE_X_PITCH, y=y_cursor
            )
            used.add(member_id)
        y_cursor -= _ROW_Y_PITCH
        if y_cursor < _DRAW_BOTTOM_ROWS:
            # Out of vertical room — remaining rows stack at the bottom.
            # v1 doesn't paginate; this is a known limit for very deep DTMs.
            y_cursor = _DRAW_BOTTOM_ROWS

    return placements


def _bus_members_source_first(bus: Bus, dtm: Dtm) -> list[str]:
    """Return member device_ids with the IEC-61850-identified source first."""
    src_idx = source_member_index(bus, dtm)
    members = [m.device_id for m in bus.members]
    if src_idx == 0:
        return members
    return [members[src_idx], *(m for i, m in enumerate(members) if i != src_idx)]

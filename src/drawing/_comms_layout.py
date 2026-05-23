"""Comms-diagram layout — protocol clusters on the A3 sheet.

Sheet origin (0,0) at bottom-left; A3 landscape modelspace 420x297 mm.
Title block consumes bottom-right 200x50mm region.

Layout rule (v1, logical topology):
- One row per protocol family present in the DTM.
- Gateway glyph at x=GATEWAY_X for each row.
- Devices arranged horizontally to the right of the gateway, max
  `DEVICES_PER_ROW` per row; wraps to a second sub-row if more.
- Cluster header (e.g. "MODBUS TCP") above each row.
- Connection lines from gateway → each device, single-stroke.
"""

from dataclasses import dataclass

# Column anchors.
GATEWAY_X: float = 40.0
DEVICES_START_X: float = 100.0
DEVICE_X_PITCH: float = 70.0
DEVICES_PER_ROW: int = 4

# Vertical placement.
TOP_ROW_Y: float = 240.0  # first cluster header sits here
HEADER_TO_ROW_GAP: float = 12.0  # cluster header sits above the gateway row
CLUSTER_Y_PITCH: float = 50.0  # between clusters (one cluster = header + row(s))
SUB_ROW_Y_PITCH: float = 22.0  # within a cluster when device count > DEVICES_PER_ROW

# Sheet bottom margin — keep gateway rows above title block + sheet frame.
MIN_GATEWAY_Y: float = 70.0


@dataclass(frozen=True)
class DeviceSlot:
    """A single device's position in the comms diagram."""

    device_id: str
    x: float
    y: float


@dataclass(frozen=True)
class ClusterPlacement:
    """One protocol cluster: header position, gateway position, device slots."""

    protocol_label: str
    header_x: float
    header_y: float
    gateway_x: float
    gateway_y: float
    devices: list[DeviceSlot]


def layout_clusters(
    devices_by_protocol: dict[str, list[str]],
) -> list[ClusterPlacement]:
    """Stack one cluster per protocol top-to-bottom.

    `devices_by_protocol` is an ordered mapping (insertion order
    preserved) of human-readable protocol label -> list of device_ids.
    """
    clusters: list[ClusterPlacement] = []
    y_cursor = TOP_ROW_Y
    for label, device_ids in devices_by_protocol.items():
        if y_cursor < MIN_GATEWAY_Y:
            # Out of vertical room; v1 doesn't paginate. Stack remaining
            # clusters at the bottom margin so they don't collide with
            # the title block.
            y_cursor = MIN_GATEWAY_Y
        slots: list[DeviceSlot] = []
        for i, did in enumerate(device_ids):
            sub_row = i // DEVICES_PER_ROW
            col = i % DEVICES_PER_ROW
            slot_x = DEVICES_START_X + col * DEVICE_X_PITCH
            slot_y = y_cursor - sub_row * SUB_ROW_Y_PITCH
            slots.append(DeviceSlot(device_id=did, x=slot_x, y=slot_y))
        clusters.append(
            ClusterPlacement(
                protocol_label=label,
                header_x=GATEWAY_X,
                header_y=y_cursor + HEADER_TO_ROW_GAP,
                gateway_x=GATEWAY_X,
                gateway_y=y_cursor,
                devices=slots,
            )
        )
        # Next cluster starts one pitch below + extra for any wrapped sub-rows.
        sub_rows = max(1, (len(device_ids) + DEVICES_PER_ROW - 1) // DEVICES_PER_ROW)
        y_cursor -= CLUSTER_Y_PITCH + (sub_rows - 1) * SUB_ROW_Y_PITCH
    return clusters

"""Parse graphviz `plain` format output into device positions.

`dot -Tplain` emits one line per graph/node/edge:
    graph <scale> <width> <height>
    node <name> <x> <y> <width> <height> <label> <style> <shape> <color> <fillcolor>
    edge ...
    stop

Coordinates are in inches (72pt = 1in). We keep them as-is and let the SVG
author convert to viewBox units.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DevicePosition:
    """Layout result for one device in inches (graphviz native units)."""

    device_id: str
    x: float
    y: float
    width: float
    height: float


def layout_devices(plain: str) -> dict[str, DevicePosition]:
    """Parse graphviz plain-format text → {device_id: DevicePosition}."""
    out: dict[str, DevicePosition] = {}
    for line in plain.splitlines():
        parts = line.split()
        if not parts or parts[0] != "node":
            continue
        # node <name> <x> <y> <width> <height> ...
        device_id = parts[1]
        out[device_id] = DevicePosition(
            device_id=device_id,
            x=float(parts[2]),
            y=float(parts[3]),
            width=float(parts[4]),
            height=float(parts[5]),
        )
    return out

"""Utility-facing devices: DER dispatch and the operating envelope.

ems-der-control-api receives the utility's IEEE 2030.5 controls and
publishes them under these fixed device ids; a grid-connected site needs
both in its device data so device-api and the HMI see flex calls and limits.
"""

from typing import Final

from src.shared.enums import GridPath
from src.shared.schemas.dtm import Device
from src.shared.schemas.module_resolution import ModuleResolution

# Reason: der-control-api's publish topics use these ids verbatim.
UTILITY_DEVICES: Final[dict[str, str]] = {
    "der_dispatch": "DER-DISPATCH",
    "operating_envelope": "OPERATING-ENVELOPE",
}


def emit_utility_devices(
    resolution: ModuleResolution, devices: dict[str, Device]
) -> None:
    """Add der_dispatch + operating_envelope unless the site is off grid."""
    if resolution.grid.path == GridPath.OFF_GRID:
        return
    for device_id, name in UTILITY_DEVICES.items():
        devices[device_id] = Device(
            device_id=device_id, template=device_id, display_name=name
        )

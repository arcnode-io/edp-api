"""Comms runs: the management network of ADR-019.

Every polled device patches to its own container's management switch;
the battery's controller patches to G1's. Compute and feeder grid
switches uplink to G1 over fiber (separate structures); G1 uplinks to
the EMS gateway host (by others).
"""

from typing import Final

from src.cable_hose_schedule._site_index import Container, tag
from src.cable_hose_schedule.cable_hose_schedule_models import CableEntry
from src.shared.schemas.dtm import Device, Dtm

_MGMT_SWITCHES: Final[tuple[str, ...]] = ("mgmt_switch", "grid_mgmt_switch")
_PROTOCOL: Final[dict[str, str]] = {
    "modbus_tcp": "Modbus TCP",
    "dnp3_tcp": "DNP3 TCP",
    "snmp": "SNMP",
    "redfish": "Redfish",
}
_COPPER: Final[str] = "Cat6 STP"
_FIBER: Final[str] = "Single-mode fiber pair, LC duplex"


def comms_cables(dtm: Dtm, sites: list[Container]) -> list[CableEntry]:
    """Device patches, then switch uplinks."""
    grids = [c for c in sites if c.kind == "grid"]
    g1 = grids[0].one(*_MGMT_SWITCHES) if grids else None
    cables: list[CableEntry] = []
    used: dict[str, int] = {}  # switch tag → ports patched so far
    for container in sites:
        switch = g1 if container.kind == "bess" else container.one(*_MGMT_SWITCHES)
        polled = [d for d in container.devices if d.connection is not None]
        if switch is None:
            if polled:
                raise ValueError(
                    f"{container.tag} has polled devices but no management switch"
                )
            continue
        for device in polled:
            used[tag(switch)] = used.get(tag(switch), 0) + 1
            cables.append(_patch(dtm, device, switch, used[tag(switch)]))
    if g1 is None:
        return cables
    for container in sites:
        switch = container.one(*_MGMT_SWITCHES)
        if switch is not None and switch is not g1:
            cables.append(
                _uplink(switch, tag(g1), _FIBER, "Separate structures: fiber.")
            )
    cables.append(
        _uplink(g1, "EMS-GW", _COPPER, "EMS gateway host by others (ADR-019).")
    )
    return cables


def _patch(dtm: Dtm, device: Device, switch: Device, port: int) -> CableEntry:
    protocol = _protocol(dtm, device)
    return CableEntry(
        tag="",
        service=f"Comms - {protocol}",
        from_device=tag(device),
        from_port="MGMT",
        to_device=tag(switch),
        to_port=f"1/{port}",
        cable_type=_COPPER,
        notes="Address assigned at commissioning.",
    )


def _uplink(switch: Device, to: str, cable: str, notes: str) -> CableEntry:
    return CableEntry(
        tag="",
        service="Comms - management uplink",
        from_device=tag(switch),
        from_port="UPLINK",
        to_device=to,
        to_port="DOWNLINK",
        cable_type=cable,
        notes=notes,
    )


def _protocol(dtm: Dtm, device: Device) -> str:
    template = dtm.templates_used[device.template]
    for measurement in template.measurements.values():
        proto = getattr(measurement.binding, "protocol", None)
        if proto in _PROTOCOL:
            return _PROTOCOL[proto]
    return "management"

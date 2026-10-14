"""DTM lookups for the comms sheets: which devices, which protocol, which address."""

from src.shared.schemas.dtm import PROVISIONED_AT_COMMISSIONING, Device, Dtm

# Binding.protocol literal → label on the sheet
_PROTOCOL_LABELS: dict[str, str] = {
    "modbus_tcp": "MODBUS TCP",
    "dnp3_tcp": "DNP3 TCP",
    "snmp": "SNMP",
    "redfish": "REDFISH",
    "canopen_gw": "CANOPEN GW",
    "synthetic": "DERIVED",
}


def networked_children(dtm: Dtm, parent: str) -> list[Device]:
    """Devices under `parent` that sit on the network (have a connection)."""
    return [
        d
        for d in dtm.devices.values()
        if d.parent == parent and d.connection is not None
    ]


def device_lines(dtm: Dtm, device: Device) -> list[str]:
    """Box text: site tag (C1-NODE-1), protocol, address (TBD until commissioning)."""
    tag = device.display_name or device.device_id
    return [tag, _protocol(dtm, device), _address(device)]


def _protocol(dtm: Dtm, device: Device) -> str:
    """Protocol of the template's first bound measurement."""
    template = dtm.templates_used[device.template]
    for measurement in template.measurements.values():
        proto = getattr(measurement.binding, "protocol", None)
        if proto in _PROTOCOL_LABELS:
            return _PROTOCOL_LABELS[proto]
    return "NO BINDING"


def _address(device: Device) -> str:
    conn = device.connection
    if conn is None or PROVISIONED_AT_COMMISSIONING in (str(conn.host), str(conn.port)):
        return "ADDR TBD"
    return f"{conn.host}:{conn.port}"

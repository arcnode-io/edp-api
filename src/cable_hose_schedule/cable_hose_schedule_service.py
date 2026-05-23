"""CableHoseScheduleService — derives cable + hose schedule from the DTM.

Produces JSON (canonical) + XLSX (reviewer-friendly) outputs at the
reserved cable_hose_schedule URLs.

v1 derives only **comms cables** from `Device.connection` + the first
template binding's protocol. Each bound device gets one Cat6/serial
cable row from the device terminating at the rack's local **network
switch** — NOT at the gateway. The gateway (cloud or on-prem) sits
behind the switch and is not a cable endpoint by physical convention.

If the DTM doesn't include a `network_switch` device, every cable's
`to_device` falls back to `TBD-LOCAL-SWITCH` so a reviewer sees the
explicit gap rather than wondering where the cables actually terminate.

Power cables and hoses are reserved for v2 once:
- BOM lines surface electrical wire/conduit entries cleanly, and
- DTM Bus schema grows a `liquid` type so coolant hoses become
  derivable from the same source as the P&ID.

The xlsx ships with both Cables and Hoses sheets — Hoses gets header-row-only
in v1 so a reviewer sees the explicit placeholder rather than wondering
whether hoses were dropped silently.
"""

from datetime import UTC, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from src.cable_hose_schedule.cable_hose_schedule_models import (
    CableEntry,
    CableHoseSchedule,
    HoseEntry,
)
from src.shared.schemas.dtm import Device, Dtm
from src.shared.schemas.template import DeviceTemplate

# Protocol → cable type mapping. All IP-based protocols share Cat6 STP at v1
# (could split out fiber per spec later). CANopen is canbus-twisted-pair.
_PROTOCOL_CABLE_TYPE: dict[str, tuple[str, str]] = {
    # protocol -> (service label, cable type)
    "modbus_tcp": ("Comms - Modbus TCP", "Cat6 STP"),
    "dnp3_tcp": ("Comms - DNP3 TCP", "Cat6 STP"),
    "snmp": ("Comms - SNMP", "Cat6 STP"),
    "redfish": ("Comms - Redfish", "Cat6 STP"),
    "canopen_gw": ("Comms - CANopen", "CAN bus twisted-pair"),
}

# Fallback when no `network_switch` device exists in the DTM. Honest signal
# that the cable termination is unresolved — better than naming a switch
# we don't actually know exists.
_TBD_SWITCH_DEVICE_ID: str = "TBD-LOCAL-SWITCH"
_TBD_SWITCH_PORT: str = "TBD"

# Template slug that identifies the rack's local network switch. v1 has
# one switch template; if a deployment grows multiple switch templates,
# this will need to be a set lookup.
_SWITCH_TEMPLATE_SLUG: str = "network_switch"

_CABLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tag", "Tag"),
    ("service", "Service"),
    ("from_device", "From Device"),
    ("from_port", "From Port"),
    ("to_device", "To Device"),
    ("to_port", "To Port"),
    ("cable_type", "Cable Type"),
    ("length_estimate_m", "Length (m)"),
    ("notes", "Notes"),
)

_HOSE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tag", "Tag"),
    ("service", "Service"),
    ("from_device", "From Device"),
    ("from_port", "From Port"),
    ("to_device", "To Device"),
    ("to_port", "To Port"),
    ("hose_type", "Hose Type"),
    ("length_estimate_m", "Length (m)"),
    ("notes", "Notes"),
)


class CableHoseScheduleService:
    """Walks the DTM, emits one comms cable per bound device.

    Returns a `CableHoseSchedule` Pydantic object — the caller picks the
    serialization format (mirrors `BomGeneratorService` which returns
    `Bom` + has module-level `serialize_bom_xlsx`). Pipeline dispatch
    calls `model_dump_json` for the json URL and
    `serialize_cable_hose_schedule_xlsx` for the xlsx URL.
    """

    def generate(self, dtm: Dtm) -> CableHoseSchedule:
        """Build the schedule. Caller serializes to JSON / XLSX."""
        return self._build_schedule(dtm)

    def _build_schedule(self, dtm: Dtm) -> CableHoseSchedule:
        switch_device_id = _find_local_switch(dtm)
        cables: list[CableEntry] = []
        tag_num = 0
        for device_id in sorted(dtm.devices):
            device = dtm.devices[device_id]
            if device.connection is None:
                continue
            if device_id == switch_device_id:
                # The switch itself doesn't cable to itself; its uplink to
                # the gateway / WAN router is a separate cable not modelled
                # at v1.
                continue
            template = dtm.templates_used.get(device.template)
            tag_num += 1
            cable = _cable_for_device(
                template,
                device_id,
                device,
                tag_num=tag_num,
                switch_device_id=switch_device_id,
                switch_port_num=tag_num,
            )
            if cable is not None:
                cables.append(cable)
            else:
                # Generator produced no cable for this device (e.g. unbound
                # template); roll back the tag we reserved so numbering
                # stays gap-free in the output.
                tag_num -= 1
        return CableHoseSchedule(
            deployment_uuid=dtm.deployment_uuid,
            generated_at=datetime.now(UTC),
            cables=cables,
            hoses=[],  # v1: not derivable until DTM bus schema grows a `liquid` type
        )


def _cable_for_device(
    template: DeviceTemplate | None,
    device_id: str,
    device: Device,
    *,
    tag_num: int,
    switch_device_id: str | None,
    switch_port_num: int,
) -> CableEntry | None:
    """Build one comms cable from a device's template binding + connection.

    Cable terminates at `switch_device_id` if the DTM includes a
    network_switch device; otherwise at the explicit `TBD-LOCAL-SWITCH`
    placeholder. `switch_port_num` sequentially numbers the switch's
    front-panel ports (GE0/0/N) — assignment is deterministic for a
    given DTM but doesn't reflect any real cable-routing layout.
    """
    if template is None or not template.measurements:
        return None
    if device.connection is None:
        return None
    protocol: str | None = None
    for measurement in template.measurements.values():
        if measurement.binding is not None:
            protocol = getattr(measurement.binding, "protocol", None)
            if protocol in _PROTOCOL_CABLE_TYPE:
                break
    if protocol not in _PROTOCOL_CABLE_TYPE:
        return None
    service, cable_type = _PROTOCOL_CABLE_TYPE[protocol]
    conn = device.connection
    unit_suffix = f" (unit_id={conn.unit_id})" if conn.unit_id else ""
    to_device = switch_device_id or _TBD_SWITCH_DEVICE_ID
    to_port = f"GE0/0/{switch_port_num}" if switch_device_id else _TBD_SWITCH_PORT
    return CableEntry(
        tag=f"CBL-{tag_num:04d}",
        service=service,
        from_device=device_id,
        from_port=f"{conn.host}:{conn.port}{unit_suffix}",
        to_device=to_device,
        to_port=to_port,
        cable_type=cable_type,
        length_estimate_m=None,  # field-measured per installation
        notes="",
    )


def _find_local_switch(dtm: Dtm) -> str | None:
    """First device whose template is `network_switch`. None if no switch in DTM.

    Deterministic across re-runs (sorted by device_id). v1 expects 0..1
    switches per deployment; multi-switch deployments would need a smarter
    "which device cables to which switch" policy than first-switch-wins.
    """
    for device_id in sorted(dtm.devices):
        if dtm.devices[device_id].template == _SWITCH_TEMPLATE_SLUG:
            return device_id
    return None


def serialize_cable_hose_schedule_xlsx(schedule: CableHoseSchedule) -> bytes:
    """Two sheets — Cables (one row per cable) + Hoses (header row only at v1)."""
    wb = Workbook()
    # Default sheet becomes "Cables".
    cables_ws = wb.active
    cables_ws.title = "Cables"
    _write_table(cables_ws, _CABLE_COLUMNS, schedule.cables)

    hoses_ws = wb.create_sheet(title="Hoses")
    _write_table(hoses_ws, _HOSE_COLUMNS, schedule.hoses)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_table(
    ws: Worksheet,
    columns: tuple[tuple[str, str], ...],
    rows: list[CableEntry] | list[HoseEntry],
) -> None:
    """Write a header row + one data row per Pydantic entry."""
    bold = Font(bold=True)
    for col_idx, (_field, label) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font = bold
    for row_idx, entry in enumerate(rows, start=2):
        for col_idx, (field, _label) in enumerate(columns, start=1):
            value = getattr(entry, field)
            # Reason: openpyxl can't write None — store as blank string.
            ws.cell(
                row=row_idx, column=col_idx, value=value if value is not None else ""
            )

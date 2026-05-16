"""Shared fixture builders for src/drawing/ TDD tests."""

from uuid import UUID

from src.shared.schemas.dtm import (
    Bus,
    BusMember,
    Connection,
    Device,
    Dtm,
    EmsMode,
    SizingParams,
)
from src.shared.schemas.template import DeviceTemplate, Measurement, TemplateKind
from src.shared.schemas.template_protocols import ModbusBinding

_DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000010")


def _modbus() -> ModbusBinding:
    return ModbusBinding(protocol="modbus_tcp", function_code=4, address=100)


def make_template(
    slug: str = "bess_rack", iec_61850_ref: str | None = None
) -> DeviceTemplate:
    """Minimal leaf template with one float measurement.

    `iec_61850_ref` on the measurement marks this template as a power source
    when set to `MMXU.W` — used by the SLD HMI SVG bus-direction rule.
    """
    return DeviceTemplate(
        template=slug,
        kind=TemplateKind.LEAF,
        equipment_id=f"EXT-{slug.upper()}-001",
        vendor="Tesla",
        model="Megapack",
        description=f"{slug} test fixture",
        measurements={
            "power": Measurement(
                unit="watts",
                type="float",
                iec_61850_ref=iec_61850_ref,
                binding=_modbus(),
            )
        },
    )


def make_device(
    device_id: str,
    template: str = "bess_rack",
    display_name: str | None = None,
) -> Device:
    """Build a Device with a sane default Modbus connection."""
    return Device(
        device_id=device_id,
        template=template,
        display_name=display_name,
        connection=Connection(host="10.0.0.1", port=502, unit_id="1"),
    )


def make_bus(bus_id: str, member_ids: list[str], bus_type: str = "dc") -> Bus:
    """Build a Bus with the given member device_ids."""
    return Bus(
        bus_id=bus_id,
        type=bus_type,  # ty: ignore[invalid-argument-type]
        members=[BusMember(device_id=mid) for mid in member_ids],
    )


def make_dtm(
    devices: dict[str, Device],
    buses: list[Bus] | None = None,
    templates: dict[str, DeviceTemplate] | None = None,
) -> Dtm:
    """Build a Dtm; auto-derives templates_used from device.template slugs."""
    if templates is None:
        slugs = {d.template for d in devices.values()}
        templates = {slug: make_template(slug) for slug in slugs}
    return Dtm(
        deployment_uuid=_DEPLOYMENT_ID,
        ems_mode=EmsMode.SIM,
        sizing_params=SizingParams(
            P_compute_total_kW=10.0,
            E_BESS_total_kWh=5000.0,
            T_coolant_setpoint_C=30.0,
        ),
        devices=devices,
        buses=buses or [],
        templates_used=templates,
    )

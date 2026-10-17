"""The battery pad: the customer's battery and, on dc_ext, the PCS beside it."""

from math import ceil
from typing import Final

from src.dtm.dtm_generator_internals import assign_slug
from src.shared.enums import BessCoupling
from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    Connection,
    Device,
)
from src.shared.schemas.module_resolution import ModuleResolution
from src.shared.schemas.template import DeviceTemplate

# CATL's ETH board answers as Modbus unit 0x64 (bess_catl.yaml)
CATL_BMS_UNIT_ID: Final[str] = "100"


def emit_battery(
    resolution: ModuleResolution,
    catalog: dict[str, DeviceTemplate],
    devices: dict[str, Device],
    slug_counter: dict[str, int],
) -> str:
    """The battery pad: a battery module holding BESS-1 (and on dc_ext, the PCS).

    The EMS supervises the customer's battery (ADR-001), so it's in the
    device data even though ARCNODE doesn't supply it. Megapack (AC) is one
    device per unit, enough units for the ordered energy, each polled over
    Modbus TCP once commissioning gives it an address; device-api derives
    the module's dispatch range from their summed ratings. CATL (DC) is one
    device for the bank, polled at its BMS's fixed Modbus unit (unverified
    map, see bess_catl.yaml). On dc_ext the pad also holds
    the PCS, PCS-1…PCS-N, one per grid container (ADR-022), polled over
    SunSpec (the gateway discovers the models).

    Returns:
        The battery module's device_id.
    """
    ac = resolution.bess_coupling == BessCoupling.AC_COUPLED
    # Reason: the DC module has no rack rollups — one CATL leaf is the bank.
    module_template = "bess_module" if ac else "bess_module_dc"
    module = assign_slug(module_template, slug_counter)
    devices[module] = Device(
        device_id=module, template=module_template, display_name="BESS"
    )
    if ac:
        _emit_megapacks(resolution, catalog["bess_rack"], module, devices, slug_counter)
    else:
        leaf = assign_slug("bess_catl", slug_counter)
        devices[leaf] = Device(
            device_id=leaf,
            template="bess_catl",
            display_name="BESS-1",
            parent=module,
            # Reason: one device is the whole bank, sized by the order
            capacity_kwh=resolution.bess_capacity_mwh * 1000,
            connection=Connection(
                host=PROVISIONED_AT_COMMISSIONING,
                port=PROVISIONED_AT_COMMISSIONING,
                unit_id=CATL_BMS_UNIT_ID,
            ),
        )
    if resolution.bess_coupling == BessCoupling.DC_EXTERNAL_PCS:
        for n in range(1, resolution.grid_container_count + 1):
            pcs = assign_slug("pcs", slug_counter)
            devices[pcs] = Device(
                device_id=pcs,
                template="pcs",
                display_name=f"PCS-{n}",
                parent=module,
                connection=Connection(
                    host=PROVISIONED_AT_COMMISSIONING,
                    port=PROVISIONED_AT_COMMISSIONING,
                ),
            )
    return module


def _emit_megapacks(
    resolution: ModuleResolution,
    megapack: DeviceTemplate,
    module: str,
    devices: dict[str, Device],
    slug_counter: dict[str, int],
) -> None:
    """BESS-1-MP-1…N: one Megapack per capacity_kwh of ordered energy, rounded up.

    The customer picks the real battery (ADR-001), so the count is the
    smallest Megapack 2 XL fleet that holds the ordered energy.
    """
    if megapack.capacity_kwh is None:
        raise ValueError("bess_rack template needs capacity_kwh to size the fleet")
    units = ceil(resolution.bess_capacity_mwh * 1000 / megapack.capacity_kwh)
    for n in range(1, units + 1):
        rack = assign_slug("bess_rack", slug_counter)
        devices[rack] = Device(
            device_id=rack,
            template="bess_rack",
            display_name=f"BESS-1-MP-{n}",
            parent=module,
            connection=Connection(
                host=PROVISIONED_AT_COMMISSIONING, port=PROVISIONED_AT_COMMISSIONING
            ),
        )

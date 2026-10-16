"""The battery pad: the customer's battery and, on dc_ext, ARCNODE's PCS."""

from src.dtm.dtm_generator_internals import assign_slug
from src.shared.enums import BessCoupling
from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    Connection,
    Device,
)


def emit_battery(
    coupling: BessCoupling,
    devices: dict[str, Device],
    slug_counter: dict[str, int],
    *,
    grid_container_count: int,
) -> str:
    """The battery pad: a battery module holding BESS-1 (and on dc_ext, the PCS).

    The EMS supervises the customer's battery (ADR-001), so it's in the
    device data even though ARCNODE doesn't supply it. Megapack (AC) is
    polled over Modbus TCP and waits for its commissioning-time address;
    CATL (DC) is passive until its BMS map is verified. On dc_ext the pad
    also holds ARCNODE's PCS, PCS-1…PCS-N, one per grid container
    (ADR-022), passive until EPC's register map is in hand.

    Returns:
        The battery module's device_id.
    """
    ac = coupling == BessCoupling.AC_COUPLED
    # Reason: the DC module has no rack rollups — its CATL leaf is passive.
    module_template = "bess_module" if ac else "bess_module_dc"
    module = assign_slug(module_template, slug_counter)
    devices[module] = Device(
        device_id=module, template=module_template, display_name="BESS"
    )
    template = "bess_rack" if ac else "bess_catl"
    leaf = assign_slug(template, slug_counter)
    devices[leaf] = Device(
        device_id=leaf,
        template=template,
        display_name="BESS-1",
        parent=module,
        connection=(
            Connection(
                host=PROVISIONED_AT_COMMISSIONING, port=PROVISIONED_AT_COMMISSIONING
            )
            if ac
            else None
        ),
    )
    if coupling == BessCoupling.DC_EXTERNAL_PCS:
        for n in range(1, grid_container_count + 1):
            pcs = assign_slug("pcs", slug_counter)
            devices[pcs] = Device(
                device_id=pcs, template="pcs", display_name=f"PCS-{n}", parent=module
            )
    return module

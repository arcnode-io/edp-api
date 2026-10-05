"""Private helpers for DtmGeneratorService — split for 200-line budget."""

import logging
from typing import Final

from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.dtm.topology_yaml import (
    TopologyBusSpec,
    TopologyYaml,
)
from src.shared.schemas.alarm import Alarm, load_alarms_from_spec
from src.shared.schemas.dtm import (
    Bus,
    BusMember,
    Connection,
    Device,
    SizingParams,
)
from src.shared.schemas.module_resolution import ModuleResolution
from src.shared.schemas.template import DeviceTemplate
from src.sizing.sizing_internals import (
    firm_onsite_mw,
    flex_energy_mwh,
    grid_peak_mw,
    recharge_mw,
    reserve_mwh,
    site_peak_mw,
)

logger = logging.getLogger(__name__)

_T_COOLANT_SETPOINT_C: Final[float] = 30.0

_MODULE_TEMPLATE_BY_ASSEMBLY_TYPE: Final[dict[str, str]] = {
    "compute_container": "compute_module",
    "grid_container": "grid_module",
}


def emit_container(
    *,
    client: ManifestClient,
    manifest: Manifest,
    asm_type: str,
    variant: str,
    devices: dict[str, Device],
    buses: list[Bus],
    slug_counter: dict[str, int],
    by_template: dict[str, list[str]],
) -> None:
    """Emit a module Device + its leaf children into devices/buses/counters."""
    module_template = _MODULE_TEMPLATE_BY_ASSEMBLY_TYPE[asm_type]
    module_slug = assign_slug(module_template, slug_counter)
    devices[module_slug] = Device(
        device_id=module_slug,
        template=module_template,
        parent=None,
        connection=None,
    )
    by_template.setdefault(module_template, []).append(module_slug)

    topology = fetch_topology(client, manifest, asm_type, variant)
    if topology is None:
        return

    for spec in topology.devices:
        slug = assign_slug(spec.template, slug_counter)
        conn = spec.connection
        devices[slug] = Device(
            device_id=slug,
            template=spec.template,
            parent=module_slug,
            connection=(
                Connection(host=conn.host, port=conn.port, unit_id=conn.unit_id)
                if conn is not None
                else None
            ),
        )
        by_template.setdefault(spec.template, []).append(slug)

    buses.extend(expand_bus(bus_spec, by_template) for bus_spec in topology.buses)


def fetch_topology(
    client: ManifestClient,
    manifest: Manifest,
    asm_type: str,
    variant: str,
) -> TopologyYaml | None:
    """Fetch + parse topology yaml for an assembly type/variant, or None."""
    type_map = manifest.assemblies.get(asm_type, {})
    av = type_map.get(variant)
    if av is None or av.topology_yaml is None:
        logger.warning(
            f"topology_yaml missing for {asm_type}/{variant} — skipping devices"
        )
        return None
    raw = client.fetch_topology_yaml(av.topology_yaml)
    return TopologyYaml.model_validate(raw)


def assign_slug(template: str, counter: dict[str, int]) -> str:
    """Increment the site-wide per-template counter and return the slug."""
    n = counter.get(template, 0) + 1
    counter[template] = n
    return f"{template}_{n}"


def expand_bus(bus_spec: TopologyBusSpec, by_template: dict[str, list[str]]) -> Bus:
    """Expand template-pattern bus members into concrete device_id BusMember entries."""
    members: list[BusMember] = [
        BusMember(device_id=device_id, port=ms.port)
        for ms in bus_spec.members
        for device_id in by_template.get(ms.device_template, [])
    ]
    return Bus(bus_id=bus_spec.bus_id, type=bus_spec.type, members=members)


def collect_templates_used(
    devices: dict[str, Device],
    catalog: dict[str, DeviceTemplate],
    *,
    client: ManifestClient,
    manifest: Manifest,
) -> dict[str, DeviceTemplate]:
    """Build templates_used; attach per-SKU alarms[] from equipment_spec.yaml.

    Modules (kind=module, no equipment_id) get the template unchanged.
    Leaves whose equipment_id is not in manifest.specs surface with empty
    alarms (specs may be still being curated; degrade quiet, log).
    """
    slugs = {d.template for d in devices.values()}
    result: dict[str, DeviceTemplate] = {}
    for slug in slugs:
        if slug not in catalog:
            raise ValueError(f"device references template {slug!r} not in catalog")
        template = catalog[slug]
        alarms = _load_alarms_for_template(template, client, manifest)
        result[slug] = template.model_copy(update={"alarms": alarms})
    return result


def _load_alarms_for_template(
    template: DeviceTemplate, client: ManifestClient, manifest: Manifest
) -> list[Alarm]:
    """Fetch equipment_spec for this leaf and extract alarms[]."""
    if template.equipment_id is None:
        return []
    spec_url = manifest.specs.get(template.equipment_id)
    if spec_url is None:
        logger.warning(
            "spec URL missing for %s; templates_used[%s].alarms = []",
            template.equipment_id,
            template.template,
        )
        return []
    return load_alarms_from_spec(client.fetch_spec(spec_url))


def sizing(resolution: ModuleResolution) -> SizingParams:
    """Compute SizingParams from resolution.

    Reason: compute load and bess_reserve_floor_mwh both come from the same
    pure sizing_internals math the configurator's sizing-preview endpoint uses
    (site_peak = whole containers x CONTAINER_KW) — one per-container figure,
    so the load the reserve is sized against is the load the DTM declares, and
    both match what the operator already saw in preview.
    """
    peak = site_peak_mw(resolution.gpu_variant, resolution.gpu_count)
    firm = firm_onsite_mw(resolution.onsite_generation)
    g_peak = grid_peak_mw(site_peak=peak, firm_onsite=firm)
    e_reserve = reserve_mwh(
        ride_through_hours=resolution.ride_through_hours, grid_peak_mw=g_peak
    )
    # Reason: Grid guarantees flex_obligation is set iff the path is flexible.
    flex = resolution.grid.flex_obligation
    e_flex = (
        0.0
        if flex is None
        else flex_energy_mwh(grid_peak_mw=g_peak, flex_obligation=flex)
    )
    p_recharge = (
        0.0 if flex is None else recharge_mw(e_flex_mwh=e_flex, flex_obligation=flex)
    )
    return SizingParams(
        P_compute_total_kW=peak * 1000,
        E_BESS_total_kWh=resolution.bess_capacity_mwh * 1000,
        T_coolant_setpoint_C=_T_COOLANT_SETPOINT_C,
        ride_through_hours=resolution.ride_through_hours,
        bess_reserve_floor_mwh=e_reserve,
        compute_shed_enabled=resolution.compute_shed_enabled,
        bess_readiness_mwh=e_reserve + e_flex,
        bess_recharge_mw=p_recharge,
    )

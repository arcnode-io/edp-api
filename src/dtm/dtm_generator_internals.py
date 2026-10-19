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
)
from src.shared.schemas.template import DeviceTemplate

logger = logging.getLogger(__name__)

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
    container_tag: str,
    drop_tags: frozenset[str] = frozenset(),
) -> None:
    """Emit a module Device + its leaf children into devices/buses/counters.

    container_tag (C1, G2, ...) is the module's display name and prefixes
    each child's topology tag, so every device has one site-unique tag.
    drop_tags are topology tags left out (a partial compute container).
    """
    topology = fetch_topology(client, manifest, asm_type, variant)
    module_template = (
        topology.module_template
        if topology is not None and topology.module_template is not None
        else _MODULE_TEMPLATE_BY_ASSEMBLY_TYPE[asm_type]
    )
    module_slug = assign_slug(module_template, slug_counter)
    devices[module_slug] = Device(
        device_id=module_slug,
        template=module_template,
        display_name=container_tag,
        parent=None,
        connection=None,
    )
    by_template.setdefault(module_template, []).append(module_slug)
    if topology is None:
        return

    # Reason: buses join this container's devices only, not every same-template
    # device emitted so far (a site can hold several grid containers).
    local_by_template: dict[str, list[str]] = {}
    for spec in topology.devices:
        if spec.tag in drop_tags:
            continue
        slug = assign_slug(spec.template, slug_counter)
        conn = spec.connection
        devices[slug] = Device(
            device_id=slug,
            template=spec.template,
            display_name=f"{container_tag}-{spec.tag}" if spec.tag else None,
            parent=module_slug,
            connection=(
                Connection(host=conn.host, port=conn.port, unit_id=conn.unit_id)
                if conn is not None
                else None
            ),
        )
        by_template.setdefault(spec.template, []).append(slug)
        local_by_template.setdefault(spec.template, []).append(slug)

    for bus_spec in topology.buses:
        bus = expand_bus(bus_spec, local_by_template)
        # Numbered like device slugs, so each container's bus id is unique
        buses.append(
            bus.model_copy(update={"bus_id": assign_slug(bus.bus_id, slug_counter)})
        )


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

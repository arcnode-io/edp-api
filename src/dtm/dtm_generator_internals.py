"""Private helpers for DtmGeneratorService — split for 200-line budget."""

import logging
from typing import Final

from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.dtm.topology_yaml import (
    TopologyBusSpec,
    TopologyYaml,
)
from src.shared.enums import GpuVariant
from src.shared.schemas.dtm import (
    Bus,
    BusMember,
    Connection,
    Device,
    SizingParams,
)
from src.shared.schemas.module_resolution import ModuleResolution
from src.shared.schemas.template import DeviceTemplate

logger = logging.getLogger(__name__)

_P_PER_GPU_KW: Final[dict[GpuVariant, float]] = {
    GpuVariant.H100_SXM: 0.7,
    GpuVariant.B200: 1.0,
}
_PUE: Final[float] = 1.3
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
        devices[slug] = Device(
            device_id=slug,
            template=spec.template,
            parent=module_slug,
            connection=Connection(
                host=spec.connection.host,
                port=spec.connection.port,
                unit_id=spec.connection.unit_id,
            ),
            blocking=list(spec.blocking),
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
    devices: dict[str, Device], catalog: dict[str, DeviceTemplate]
) -> dict[str, DeviceTemplate]:
    """Build templates_used map from catalog, raising if any slug is missing."""
    slugs = {d.template for d in devices.values()}
    result: dict[str, DeviceTemplate] = {}
    for slug in slugs:
        if slug not in catalog:
            raise ValueError(f"device references template {slug!r} not in catalog")
        result[slug] = catalog[slug]
    return result


def sizing(resolution: ModuleResolution) -> SizingParams:
    """Compute SizingParams from resolution. PUE + per-gpu kW are PM placeholders."""
    per_gpu_kw = _P_PER_GPU_KW[resolution.gpu_variant]
    return SizingParams(
        P_compute_total_kW=resolution.gpu_count * per_gpu_kw * _PUE,
        E_BESS_total_kWh=resolution.bess_capacity_mwh * 1000,
        T_coolant_setpoint_C=_T_COOLANT_SETPOINT_C,
    )

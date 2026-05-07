"""DtmGeneratorService — fetches manifest + topology yamls, emits Dtm.

Per ADR-006 + Q16 step 6.6: consumes the same manifest as bom_generator.
Mirrors BomGeneratorService pattern. Builds a Dtm in SIM mode;
ems-device-api flips to LIVE mode at commissioning.
"""

import logging
from typing import Final
from uuid import uuid4

from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.dtm.topology_yaml import TopologyYaml
from src.shared.enums import GpuVariant
from src.shared.schemas.dtm import (
    Device,
    Dtm,
    EmsMode,
    Module,
    SizingParams,
)
from src.shared.schemas.module_resolution import ModuleResolution

logger = logging.getLogger(__name__)

# Per-GPU power draw (kW) — sales/PM placeholders.
_P_PER_GPU_KW: Final[dict[GpuVariant, float]] = {
    GpuVariant.H100_SXM: 0.7,
    GpuVariant.B200: 1.0,
}
_PUE: Final[float] = 1.3
_T_COOLANT_SETPOINT_C: Final[float] = 30.0


class DtmGeneratorService:
    """Builds a Dtm in SIM mode. ems-device-api owns later LIVE rewrites."""

    def __init__(self, manifest_client: ManifestClient) -> None:
        self._client = manifest_client

    def generate(self, *, profile: str, resolution: ModuleResolution) -> Dtm:
        """Compose modules + devices from manifest topology yamls + resolution.

        Args:
            profile: Profile name (e.g. "commercial_ac"). Must exist in manifest.
            resolution: ModuleResolution with deployment_id, container counts,
                BESS coupling, gpu_variant/count, climate_zone, etc.

        Returns:
            Dtm in SIM mode with modules + devices populated.

        Raises:
            ValueError: If profile is not in the manifest.
        """
        manifest = self._client.fetch_manifest()
        if profile not in manifest.profiles:
            raise ValueError(
                f"profile {profile!r} not in manifest "
                f"(available: {sorted(manifest.profiles)})"
            )
        prof = manifest.profiles[profile]

        modules: list[Module] = []
        devices: list[Device] = []

        compute_topology = self._fetch_topology_for(
            manifest, "compute_container", prof.compute_container
        )
        for i in range(resolution.compute_container_count):
            module_id = f"compute_container_{i + 1}"
            modules.append(self._compute_module(module_id, i + 1))
            if compute_topology is not None:
                devices.extend(self._instantiate_devices(compute_topology, module_id))

        if prof.grid_container is not None:
            grid_topology = self._fetch_topology_for(
                manifest, "grid_container", prof.grid_container
            )
            module_id = "grid_container_1"
            modules.append(self._grid_module(module_id))
            if grid_topology is not None:
                devices.extend(self._instantiate_devices(grid_topology, module_id))

        return Dtm(
            deployment_uuid=resolution.deployment_id,
            ems_mode=EmsMode.SIM,
            sizing_params=self._sizing(resolution),
            modules=modules,
            devices=devices,
        )

    def _fetch_topology_for(
        self, manifest: Manifest, asm_type: str, variant: str
    ) -> TopologyYaml | None:
        """Look up topology_yaml URL in manifest, fetch + parse, or return None."""
        type_map = manifest.assemblies.get(asm_type, {})
        av = type_map.get(variant)
        if av is None or av.topology_yaml is None:
            logger.warning(
                f"topology_yaml missing for {asm_type}/{variant} — skipping devices"
            )
            return None
        raw = self._client.fetch_topology_yaml(av.topology_yaml)
        return TopologyYaml.model_validate(raw)

    @staticmethod
    def _compute_module(module_id: str, position: int) -> Module:
        return Module(
            module_id=module_id,
            module_type="compute_container",
            container_position=f"position_{position}",
            description=f"Compute container {position}",
        )

    @staticmethod
    def _grid_module(module_id: str) -> Module:
        return Module(
            module_id=module_id,
            module_type="grid_container",
            container_position="position_grid",
            description="Grid container",
        )

    @staticmethod
    def _instantiate_devices(topology: TopologyYaml, module_id: str) -> list[Device]:
        return [
            Device(
                device_uuid=uuid4(),
                device_type=spec.device_type,
                module_id=module_id,
                host=spec.host,
                port=spec.port,
                protocol_config=spec.protocol_config,
                description=spec.description,
            )
            for spec in topology.devices
        ]

    @staticmethod
    def _sizing(resolution: ModuleResolution) -> SizingParams:
        # Reason: placeholder PUE + per-gpu kW; PM can refine later.
        per_gpu_kw = _P_PER_GPU_KW[resolution.gpu_variant]
        return SizingParams(
            P_compute_total_kW=resolution.gpu_count * per_gpu_kw * _PUE,
            E_BESS_total_kWh=resolution.bess_capacity_mwh * 1000,
            T_coolant_setpoint_C=_T_COOLANT_SETPOINT_C,
        )

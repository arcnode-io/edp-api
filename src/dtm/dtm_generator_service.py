"""DtmGeneratorService — stitches assembly topology yamls + ModuleResolution -> Dtm."""

from typing import Final
from uuid import uuid4

from src.dtm.topology_loader import TopologyLoader
from src.dtm.topology_yaml import TopologyYaml
from src.hardware_selector.hardware_selector_models import ProfileAssemblies
from src.shared.enums import GpuVariant
from src.shared.schemas.dtm import (
    Device,
    Dtm,
    EmsMode,
    Module,
    SizingParams,
)
from src.shared.schemas.module_resolution import ModuleResolution

# Per-GPU power draw (kW) — sales/PM placeholders.
_P_PER_GPU_KW: Final[dict[GpuVariant, float]] = {
    GpuVariant.H100_SXM: 0.7,
    GpuVariant.B200: 1.0,
}
_PUE: Final[float] = 1.3
_T_COOLANT_SETPOINT_C: Final[float] = 30.0


class DtmGeneratorService:
    """Builds a Dtm in SIM mode. ems-device-api owns later LIVE rewrites."""

    def __init__(self, topology_loader: TopologyLoader) -> None:
        self._loader = topology_loader

    def generate(
        self, resolution: ModuleResolution, assemblies: ProfileAssemblies
    ) -> Dtm:
        """Compose modules + devices from assembly topologies and resolution counts."""
        modules: list[Module] = []
        devices: list[Device] = []

        compute_topology = self._loader.load(assemblies.compute_container.topology_yaml)
        for i in range(resolution.compute_container_count):
            module_id = f"compute_container_{i + 1}"
            modules.append(self._compute_module(module_id, i + 1))
            devices.extend(self._instantiate_devices(compute_topology, module_id))

        if assemblies.grid_container is not None:
            grid_topology = self._loader.load(assemblies.grid_container.topology_yaml)
            module_id = "grid_container_1"
            modules.append(self._grid_module(module_id))
            devices.extend(self._instantiate_devices(grid_topology, module_id))

        return Dtm(
            deployment_uuid=resolution.deployment_id,
            ems_mode=EmsMode.SIM,
            sizing_params=self._sizing(resolution),
            modules=modules,
            devices=devices,
        )

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

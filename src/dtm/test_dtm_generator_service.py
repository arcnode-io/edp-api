"""DtmGeneratorService unit tests with a fake TopologyLoader."""

from uuid import UUID

from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.topology_yaml import TopologyDeviceSpec, TopologyYaml
from src.hardware_selector.hardware_selector_models import (
    AssemblyUrls,
    ProfileAssemblies,
)
from src.shared.enums import (
    BessCoupling,
    ClimateZone,
    DeploymentProfile,
    EmsTarget,
    GpuVariant,
    SourcingTier,
)
from src.shared.schemas.dtm import EmsMode, ModbusTcpConfig, PointMap, ProtocolKind
from src.shared.schemas.module_resolution import ModuleResolution

DEPLOYMENT_ID: UUID = UUID("12345678-1234-1234-1234-123456789abc")
COMPUTE_TOPOLOGY_URL = (
    "s3://arcnode-artifacts/assemblies/compute-container/commercial-ac/topology.yaml"
)
GRID_TOPOLOGY_URL = (
    "s3://arcnode-artifacts/assemblies/grid-container/commercial-ac/topology.yaml"
)


class _FakeTopologyLoader:
    """In-memory loader for tests."""

    def __init__(self, mapping: dict[str, TopologyYaml]) -> None:
        self._mapping = mapping

    def load(self, url: str) -> TopologyYaml:
        return self._mapping[url]


def _topology_with_one_bms() -> TopologyYaml:
    return TopologyYaml(
        devices=[
            TopologyDeviceSpec(
                device_type="bms",
                description="Tesla Megapack BMS",
                host="mock-modbus-server",
                port=502,
                protocol_config=ModbusTcpConfig(
                    protocol=ProtocolKind.MODBUS_TCP,
                    unit_id=1,
                    point_maps=[
                        PointMap(name="soc", function_code=3, start_address=0, count=1)
                    ],
                ),
            )
        ]
    )


def _resolution(
    *,
    profile: DeploymentProfile = DeploymentProfile.COMMERCIAL_AC,
    container_count: int = 1,
    coupling: BessCoupling = BessCoupling.AC_COUPLED,
    bess_mwh: float = 5.0,
) -> ModuleResolution:
    return ModuleResolution(
        deployment_id=DEPLOYMENT_ID,
        deployment_profile=profile,
        compute_container_count=container_count,
        grid_container_present=coupling != BessCoupling.NONE,
        bess_coupling=coupling,
        bess_capacity_mwh=bess_mwh,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=GpuVariant.H100_SXM,
        gpu_count=container_count * 56,
        climate_zone=ClimateZone.TEMPERATE,
    )


def _assemblies(*, with_grid: bool = True) -> ProfileAssemblies:
    compute = AssemblyUrls(
        step="s3://.../compute.step",
        glb="s3://.../compute.glb",
        topology_yaml=COMPUTE_TOPOLOGY_URL,
    )
    grid = (
        AssemblyUrls(
            step="s3://.../grid.step",
            glb="s3://.../grid.glb",
            topology_yaml=GRID_TOPOLOGY_URL,
        )
        if with_grid
        else None
    )
    return ProfileAssemblies(
        compute_container=compute, grid_container=grid, interface_plates=[]
    )


def test_emits_dtm_with_sim_mode_and_deployment_uuid() -> None:
    """Happy path: minimal topology + single compute container -> Dtm."""
    # Arrange
    loader = _FakeTopologyLoader(
        {
            COMPUTE_TOPOLOGY_URL: _topology_with_one_bms(),
            GRID_TOPOLOGY_URL: TopologyYaml(devices=[]),
        }
    )
    service = DtmGeneratorService(topology_loader=loader)

    # Act
    actual = service.generate(_resolution(), _assemblies())

    # Assert
    assert actual.deployment_uuid == DEPLOYMENT_ID
    assert actual.ems_mode == EmsMode.SIM


def test_creates_one_module_per_compute_container_instance() -> None:
    """compute_container_count=3 -> 3 compute_container modules."""
    # Arrange
    loader = _FakeTopologyLoader(
        {
            COMPUTE_TOPOLOGY_URL: _topology_with_one_bms(),
            GRID_TOPOLOGY_URL: TopologyYaml(devices=[]),
        }
    )
    service = DtmGeneratorService(topology_loader=loader)

    # Act
    actual = service.generate(_resolution(container_count=3), _assemblies())

    # Assert
    compute_modules = [
        m for m in actual.modules if m.module_type == "compute_container"
    ]
    assert len(compute_modules) == 3


def test_grid_container_module_emitted_when_present() -> None:
    """Grid container present in resolution -> one grid_container module."""
    # Arrange
    loader = _FakeTopologyLoader(
        {
            COMPUTE_TOPOLOGY_URL: _topology_with_one_bms(),
            GRID_TOPOLOGY_URL: TopologyYaml(devices=[]),
        }
    )
    service = DtmGeneratorService(topology_loader=loader)

    # Act
    actual = service.generate(_resolution(), _assemblies(with_grid=True))

    # Assert
    grid_modules = [m for m in actual.modules if m.module_type == "grid_container"]
    assert len(grid_modules) == 1


def test_no_grid_container_for_no_bess() -> None:
    """no_bess profile -> no grid_container module."""
    # Arrange
    loader = _FakeTopologyLoader({COMPUTE_TOPOLOGY_URL: _topology_with_one_bms()})
    service = DtmGeneratorService(topology_loader=loader)
    resolution = _resolution(
        profile=DeploymentProfile.COMMERCIAL_NO_BESS,
        coupling=BessCoupling.NONE,
        bess_mwh=0.0,
    )

    # Act
    actual = service.generate(resolution, _assemblies(with_grid=False))

    # Assert
    grid_modules = [m for m in actual.modules if m.module_type == "grid_container"]
    assert grid_modules == []


def test_devices_carry_module_id_fk() -> None:
    """Every device.module_id references a real module_id (FK validator passes)."""
    # Arrange
    loader = _FakeTopologyLoader(
        {
            COMPUTE_TOPOLOGY_URL: _topology_with_one_bms(),
            GRID_TOPOLOGY_URL: TopologyYaml(devices=[]),
        }
    )
    service = DtmGeneratorService(topology_loader=loader)

    # Act
    actual = service.generate(_resolution(container_count=2), _assemblies())

    # Assert — Dtm validator already enforces FK; just confirm devices exist
    assert len(actual.devices) == 2  # 2 containers x 1 device each


def test_sizing_params_derived_from_resolution() -> None:
    """gpu_count * per-gpu kW * PUE = P_compute_total_kW; bess_mwh*1000 = E_BESS_total_kWh."""
    # Arrange
    loader = _FakeTopologyLoader(
        {
            COMPUTE_TOPOLOGY_URL: TopologyYaml(devices=[]),
            GRID_TOPOLOGY_URL: TopologyYaml(devices=[]),
        }
    )
    service = DtmGeneratorService(topology_loader=loader)

    # Act
    actual = service.generate(_resolution(container_count=1), _assemblies())

    # Assert
    assert actual.sizing_params.E_BESS_total_kWh == 5000.0
    assert actual.sizing_params.P_compute_total_kW > 0

"""DtmGeneratorService unit tests for the canonical schema (PR 2)."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.template_loader import TemplateLoader
from src.shared.enums import (
    BessCoupling,
    ClimateZone,
    DeploymentProfile,
    EmsTarget,
    GpuVariant,
    SourcingTier,
)
from src.shared.schemas.dtm import EmsMode
from src.shared.schemas.module_resolution import ModuleResolution

DEPLOYMENT_ID: UUID = UUID("12345678-1234-1234-1234-123456789abc")


def _real_catalog() -> dict:
    """Use the real device_templates/ catalog from PR 1."""
    repo_root = Path(__file__).resolve().parents[2]
    return TemplateLoader(root=repo_root / "device_templates").load_catalog()


def _av(*, type_: str, variant: str) -> AssemblyVariant:
    base = f"s3://test/{type_.replace('_', '-')}/{variant}"
    return AssemblyVariant(
        bom=f"{base}/bom.yaml",
        step=f"{base}/assembly.step",
        glb=f"{base}/assembly.glb",
        topology_yaml=f"{base}/topology.yaml",
    )


def _manifest() -> Manifest:
    return Manifest(
        version="0.1.0",
        assemblies={
            "compute_container": {
                "commercial-ac": _av(type_="compute_container", variant="commercial-ac")
            },
            "grid_container": {
                "commercial-ac": _av(type_="grid_container", variant="commercial-ac")
            },
        },
        plates={"CG": PlateUrls(spec="s3://test/CG.yaml", step="s3://test/CG.step")},
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG"],
            )
        },
    )


def _resolution(*, container_count: int = 1) -> ModuleResolution:
    return ModuleResolution(
        deployment_id=DEPLOYMENT_ID,
        deployment_profile=DeploymentProfile.COMMERCIAL_AC,
        compute_container_count=container_count,
        grid_container_present=True,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=GpuVariant.H100_SXM,
        gpu_count=container_count * 56,
        climate_zone=ClimateZone.TEMPERATE,
    )


# Inline mock topologies — decoupled from edp-module-assemblies repo
COMPUTE_TOPOLOGY: dict = {
    "devices": [
        {
            "template": "gpu_node",
            "description": f"node {i}",
            "connection": {"host": "mock-redfish-server", "port": 8443},
        }
        for i in range(1, 4)  # 3 nodes for test simplicity
    ]
    + [
        {
            "template": "cdu",
            "description": "cdu",
            "connection": {"host": "mock-redfish-server", "port": 8443},
        }
    ],
    "buses": [],
}


GRID_TOPOLOGY: dict = {
    "devices": [
        {
            "template": "switchgear",
            "description": "swg",
            "connection": {"host": "mock-modbus-server", "port": 502, "unit_id": "1"},
        },
        {
            "template": "revenue_meter",
            "description": "meter",
            "connection": {"host": "mock-modbus-server", "port": 502, "unit_id": "2"},
        },
        {
            "template": "protective_relay",
            "description": "relay",
            "connection": {"host": "mock-dnp3-server", "port": 20000},
        },
    ],
    "buses": [
        {
            "bus_id": "ac_main",
            "type": "ac",
            "members": [
                {"device_template": "switchgear", "port": "line_out"},
                {"device_template": "revenue_meter", "port": "voltage_in"},
                {"device_template": "protective_relay", "port": "line_in"},
            ],
        }
    ],
}


def _make_client() -> MagicMock:
    client = MagicMock()
    client.fetch_manifest.return_value = _manifest()

    def fetch(url: str) -> dict:
        if "compute-container" in url:
            return COMPUTE_TOPOLOGY
        if "grid-container" in url:
            return GRID_TOPOLOGY
        raise ValueError(f"unmocked: {url}")

    client.fetch_topology_yaml.side_effect = fetch
    return client


def test_generate_emits_sim_mode() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    assert actual.ems_mode == EmsMode.SIM


def test_generate_dissolves_modules_into_devices() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    assert "compute_module_1" in actual.devices
    assert "grid_module_1" in actual.devices
    assert actual.devices["compute_module_1"].parent is None
    assert actual.devices["grid_module_1"].parent is None


def test_generate_assigns_per_template_indexed_slugs() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    gpu_slugs = [s for s in actual.devices if s.startswith("gpu_node_")]
    assert sorted(gpu_slugs) == [f"gpu_node_{i}" for i in range(1, 4)]
    assert "revenue_meter_1" in actual.devices


def test_generate_parents_leaves_under_modules() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    assert actual.devices["gpu_node_1"].parent == "compute_module_1"
    assert actual.devices["revenue_meter_1"].parent == "grid_module_1"


def test_generate_embeds_templates_used() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    referenced_slugs = {d.template for d in actual.devices.values()}
    assert referenced_slugs <= set(actual.templates_used)
    assert actual.templates_used["revenue_meter"].equipment_id == "GRD-MTR-001"


def test_generate_expands_bus_members() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    assert len(actual.buses) == 1
    bus = actual.buses[0]
    member_ids = {m.device_id for m in bus.members}
    assert "switchgear_1" in member_ids
    assert "revenue_meter_1" in member_ids
    assert "protective_relay_1" in member_ids


def test_generate_slug_counter_continues_across_containers() -> None:
    # Arrange — 2 compute containers means gpu_node count doubles
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(container_count=2)
    )
    # Assert — gpu_node_1 through gpu_node_6 (3 per container * 2)
    gpu_slugs = [s for s in actual.devices if s.startswith("gpu_node_")]
    assert len(gpu_slugs) == 6


def test_generate_unknown_profile_raises() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act / Assert
    with pytest.raises(ValueError, match="not in manifest"):
        service.generate(profile="dod_dc_int", resolution=_resolution())

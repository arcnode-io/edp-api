"""Shared fixtures and helpers for DtmGeneratorService unit tests."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.dtm.template_loader import TemplateLoader
from src.shared.enums import (
    BessCoupling,
    ClimateZone,
    DeploymentProfile,
    EmsTarget,
    GpuVariant,
    SourcingTier,
)
from src.shared.schemas.module_resolution import ModuleResolution

DEPLOYMENT_ID: UUID = UUID("12345678-1234-1234-1234-123456789abc")

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

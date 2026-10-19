"""Shared fixtures and helpers for DtmGeneratorService unit tests."""

from pathlib import Path
from typing import Final
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
    GridPath,
    OnsiteGenerationType,
    SourcingTier,
)
from src.shared.schemas.configurator_grid import Grid, OnsiteGeneration
from src.shared.schemas.module_resolution import ModuleResolution
from src.dtm.dtm_test_topologies import (
    COMPUTE_TOPOLOGY,
    H100_COMPUTE_TOPOLOGY,
    GRID_TOPOLOGY,
    FEEDER_TOPOLOGY,
)

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
                "commercial-ac": _av(
                    type_="compute_container", variant="commercial-ac"
                ),
                "commercial-ac-h100": _av(
                    type_="compute_container", variant="commercial-ac-h100"
                ),
            },
            "grid_container": {
                "commercial-ac": _av(type_="grid_container", variant="commercial-ac"),
                "feeder": _av(type_="grid_container", variant="feeder"),
            },
        },
        plates={"CG": PlateUrls(spec="s3://test/CG.yaml", step="s3://test/CG.step")},
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                compute_container_by_gpu={
                    GpuVariant.B200: "commercial-ac",
                    GpuVariant.H100_SXM: "commercial-ac-h100",
                },
                grid_container="commercial-ac",
                grid_feeder_container="feeder",
                interface_plates=["CG"],
            )
        },
    )


_OFF_GRID: Final[Grid] = Grid(path=GridPath.OFF_GRID)


def _resolution(
    *,
    container_count: int = 1,
    grid_container_count: int = 1,
    ride_through_hours: float = 0.0,
    grid: Grid = _OFF_GRID,
    gpu_variant: GpuVariant = GpuVariant.B200,
) -> ModuleResolution:
    return ModuleResolution(
        deployment_id=DEPLOYMENT_ID,
        deployment_profile=DeploymentProfile.COMMERCIAL_AC,
        compute_container_count=container_count,
        gpu_node_count=container_count * 7,
        grid_container_count=grid_container_count,
        pcs_count=0,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=gpu_variant,
        gpu_count=container_count * 56,
        climate_zone=ClimateZone.TEMPERATE,
        onsite_generation=OnsiteGeneration(type=OnsiteGenerationType.NONE),
        ride_through_hours=ride_through_hours,
        compute_shed_enabled=False,
        grid=grid,
    )


def _make_client() -> MagicMock:
    client = MagicMock()
    client.fetch_manifest.return_value = _manifest()

    def fetch(url: str) -> dict:
        if "compute-container/commercial-ac-h100" in url:
            return H100_COMPUTE_TOPOLOGY
        if "compute-container" in url:
            return COMPUTE_TOPOLOGY
        if "grid-container/feeder" in url:
            return FEEDER_TOPOLOGY
        if "grid-container" in url:
            return GRID_TOPOLOGY
        raise ValueError(f"unmocked: {url}")

    client.fetch_topology_yaml.side_effect = fetch
    return client

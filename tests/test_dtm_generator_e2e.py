"""End-to-end DTM generation against real device_templates/ and assemblies/ topologies.

Skipped when the sibling `edp-module-assemblies` checkout isn't available
(e.g. CI without a multi-repo checkout). Local dev with both repos under
`~/arcnode/` runs the full pipeline.
"""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import yaml

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

# Reason: e2e covers the cross-repo contract; skip when assemblies repo absent.
# parents[0]=tests/, parents[1]=edp-api/, parents[2]=arcnode/
_ASSEMBLIES_DIR = (
    Path(__file__).resolve().parents[2] / "edp-module-assemblies/assemblies"
)
_skip_if_no_assemblies = pytest.mark.skipif(
    not _ASSEMBLIES_DIR.is_dir(),
    reason="sibling edp-module-assemblies checkout required",
)


def _client_against_real_assemblies() -> MagicMock:
    """Mocked manifest client returning the actual edp-module-assemblies topology.yamls."""
    client = MagicMock()
    client.fetch_manifest.return_value = Manifest(
        version="0.1.0",
        assemblies={
            "compute_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/compute-container/commercial-ac/bom.yaml",
                    step="s3://test/compute-container/commercial-ac/assembly.step",
                    glb="s3://test/compute-container/commercial-ac/assembly.glb",
                    topology_yaml="s3://test/compute-container/commercial-ac/topology.yaml",
                )
            },
            "grid_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/grid-container/commercial-ac/bom.yaml",
                    step="s3://test/grid-container/commercial-ac/assembly.step",
                    glb="s3://test/grid-container/commercial-ac/assembly.glb",
                    topology_yaml="s3://test/grid-container/commercial-ac/topology.yaml",
                )
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

    asm = _ASSEMBLIES_DIR

    def fetch(url: str) -> dict:  # type: ignore[type-arg]
        if "compute-container" in url:
            return yaml.safe_load(
                (asm / "compute-container/commercial-ac/topology.yaml").read_text()
            )
        if "grid-container" in url:
            return yaml.safe_load(
                (asm / "grid-container/commercial-ac/topology.yaml").read_text()
            )
        raise ValueError(url)

    client.fetch_topology_yaml.side_effect = fetch
    return client


def _resolution() -> ModuleResolution:
    return ModuleResolution(
        deployment_id=UUID("12345678-1234-1234-1234-123456789abc"),
        deployment_profile=DeploymentProfile.COMMERCIAL_AC,
        compute_container_count=1,
        grid_container_present=True,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=GpuVariant.H100_SXM,
        gpu_count=56,
        climate_zone=ClimateZone.TEMPERATE,
    )


@_skip_if_no_assemblies
def test_e2e_commercial_ac_dtm_validates() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[1]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    client = _client_against_real_assemblies()
    service = DtmGeneratorService(client, template_catalog=catalog)
    # Act
    dtm = service.generate(
        profile="commercial_ac",
        resolution=_resolution(),
        manifest=client.fetch_manifest(),
    )
    # Assert — top-level shape
    assert dtm.mode == EmsMode.LIVE
    # Module Devices exist
    assert "compute_module_1" in dtm.devices
    assert "grid_module_1" in dtm.devices
    # Compute leaves: 7 gpu_nodes + 1 cdu + 1 network_switch + 4 pdus = 13
    compute_descendants = [
        s for s, d in dtm.devices.items() if d.parent == "compute_module_1"
    ]
    assert len(compute_descendants) == 13
    # Grid leaves: 3 (switchgear, revenue_meter, protective_relay)
    grid_descendants = [
        s for s, d in dtm.devices.items() if d.parent == "grid_module_1"
    ]
    assert len(grid_descendants) == 3
    # Templates used
    assert "gpu_node" in dtm.templates_used
    assert "compute_module" in dtm.templates_used
    assert "grid_module" in dtm.templates_used
    # Buses: 1 ac_main from grid topology
    assert any(b.bus_id == "ac_main" for b in dtm.buses)
    bus = next(b for b in dtm.buses if b.bus_id == "ac_main")
    member_ids = {m.device_id for m in bus.members}
    assert "switchgear_1" in member_ids
    assert "revenue_meter_1" in member_ids
    assert "protective_relay_1" in member_ids


@_skip_if_no_assemblies
def test_e2e_pending_devices_empty_when_topology_has_no_sentinels() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[1]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    client = _client_against_real_assemblies()
    service = DtmGeneratorService(client, template_catalog=catalog)
    # Act
    dtm = service.generate(
        profile="commercial_ac",
        resolution=_resolution(),
        manifest=client.fetch_manifest(),
    )
    # Assert
    assert dtm.pending_devices == []

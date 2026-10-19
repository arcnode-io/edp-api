"""Shared builders for the pipeline tests; import explicitly."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.cable_hose_schedule.cable_hose_schedule_models import (
    CableEntry,
    CableHoseSchedule,
)
from src.cable_hose_schedule.cable_hose_schedule_service import CableHoseScheduleService
from src.drawing.comms_diagram_service import CommsDiagramService
from src.drawing.install_sequence_service import InstallSequenceService
from src.drawing.pid_cooling_service import PidCoolingService
from src.drawing.sld_engineering_service import SldEngineeringService
from src.drawing.sld_hmi_svg_service import SldHmiSvgService
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.template_loader import TemplateLoader
from src.pipeline.pipeline_service import PipelineService
from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    GpuVariant,
    GridPath,
    OnsiteGenerationType,
    PrimaryWorkload,
)
from src.shared.schemas.dtm import Dtm
from src.shared.schemas.configurator_grid import (
    Grid,
    OnsiteGeneration,
    Site,
    SiteLocation,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000abc")


class _RecordingClient:
    """Stub ManifestClient: records uploads, returns an in-memory manifest."""

    def __init__(self, manifest: Manifest) -> None:
        self._manifest = manifest
        self.uploads: dict[str, bytes] = {}

    def fetch_manifest(self) -> Manifest:
        return self._manifest

    def fetch_bom_yaml(self, _url: str) -> dict:
        # Minimum viable bom.yaml shape — a shell, the profile's plates and no
        # parts (we're testing dispatch, not BOM content).
        return {
            "shell": {"part_number": "ARC-CNT-CMP-001", "description": "shell"},
            "parts": [],
            "plates": [{"id": pid, "qty": 1} for pid in ("CG", "BG-AC", "CD")],
        }

    def fetch_topology_yaml(self, url: str) -> dict:
        # Grid containers carry their management switch, where the battery's
        # controller patches in (ADR-019), and the transformer + LV switchboard
        # their compute feeders hang off (ADR-018); otherwise no devices.
        if "grid" not in url:
            return {"devices": []}
        switch = {
            "template": "grid_mgmt_switch",
            "tag": "SW-MGMT-1",
            "description": "stub",
        }
        xfmr = {"template": "transformer", "tag": "T1", "description": "stub"}
        swbd = {"template": "lv_switchboard", "tag": "SWBD-1", "description": "stub"}
        return {"devices": [switch, xfmr, swbd]}

    def fetch_spec(self, _url: str) -> dict:
        return {}

    def upload_bom_json(self, body: bytes, target_url: str) -> None:
        self.uploads[target_url] = body

    def upload_bytes(self, body: bytes, target_url: str) -> None:
        self.uploads[target_url] = body


def _commercial_ac_manifest() -> Manifest:
    """Profile + assemblies + plates needed for commercial_ac end-to-end."""
    asm = AssemblyVariant(
        bom="s3://test/compute/commercial-ac/bom.yaml",
        step="s3://arcnode-artifacts/assemblies/compute-container/commercial-ac/assembly.step",
        glb="s3://arcnode-artifacts/assemblies/compute-container/commercial-ac/assembly.glb",
        topology_yaml="s3://test/compute/commercial-ac/topology.yaml",
    )
    grid = AssemblyVariant(
        bom="s3://test/grid/commercial-ac/bom.yaml",
        step="s3://arcnode-artifacts/assemblies/grid-container/commercial-ac/assembly.step",
        glb="s3://arcnode-artifacts/assemblies/grid-container/commercial-ac/assembly.glb",
        topology_yaml="s3://test/grid/commercial-ac/topology.yaml",
    )
    return Manifest(
        version="0.0.0-test",
        assemblies={
            "compute_container": {"commercial-ac": asm},
            "grid_container": {"commercial-ac": grid},
        },
        plates={
            pid: PlateUrls(
                spec=f"s3://arcnode-artifacts/plates/{pid}/spec.yaml",
                step=f"s3://arcnode-artifacts/plates/{pid}/{pid}.step",
                dxf=f"s3://arcnode-artifacts/plates/{pid}/{pid}.dxf",
            )
            for pid in ("CG", "BG-AC", "CD")
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "BG-AC", "CD"],
            ),
        },
    )


def _payload() -> ConfiguratorPayload:
    return ConfiguratorPayload(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=56,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=DeploymentContext.COMMERCIAL,
        aws_partition=AwsPartition.STANDARD,
        site=Site(location=SiteLocation(lat=32.7, lon=-96.8), country="US"),
        onsite_generation=OnsiteGeneration(type=OnsiteGenerationType.NONE),
        grid=Grid(path=GridPath.OFF_GRID),
    )


def _build_pipeline(
    client: _RecordingClient,
    cable_hose: CableHoseScheduleService | None = None,
) -> PipelineService:
    real_client = cast(ManifestClient, client)
    catalog = TemplateLoader(
        root=__import__("pathlib").Path(__file__).resolve().parents[2]
        / "device_templates"
    ).load_catalog()
    return PipelineService(
        client=real_client,
        bom_generator=BomGeneratorService(real_client),
        dtm_generator=DtmGeneratorService(real_client, template_catalog=catalog),
        sld_hmi_svg_service=SldHmiSvgService(),
        sld_engineering_service=SldEngineeringService(),
        pid_cooling_service=PidCoolingService(),
        comms_diagram_service=CommsDiagramService(),
        cable_hose_schedule_service=cable_hose or CableHoseScheduleService(),
        install_sequence_service=InstallSequenceService(),
    )


class _OneCableSchedule(CableHoseScheduleService):
    """Schedule with one known cable, so the BOM roll-up is observable."""

    def generate(self, dtm: Dtm) -> CableHoseSchedule:
        cable = CableEntry(
            tag="CBL-0001",
            service="Comms - Modbus TCP",
            from_device="pdu_1",
            from_port="TCP/502",
            to_device="network_switch_1",
            to_port="eth1",
            cable_type="Cat6 STP",
        )
        return CableHoseSchedule(
            deployment_uuid=dtm.deployment_uuid,
            generated_at=datetime.now(UTC),
            cables=[cable],
        )

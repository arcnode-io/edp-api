"""End-to-end test: bom_generator against localstack S3 per Q7-D + Q9-C.

Spins up localstack via testcontainers, uploads a fixture manifest +
spec.yamls + bom.yaml + plate spec.yaml, then runs BomGeneratorService
against it and asserts the resulting bom.json shape.
"""

from collections.abc import Iterator
from uuid import uuid4

import boto3
import pytest
import yaml
from testcontainers.localstack import LocalStackContainer

from src.bom_generator.bom_generator_service import (
    BomGeneratorService,
    serialize_bom,
)
from src.bom_generator.bom_models import ProcurementPath
from src.bom_generator.manifest_client import ManifestClient

BUCKET = "arcnode-artifacts"
TEST_REGION = "us-east-1"


@pytest.fixture(scope="session")
def localstack_endpoint() -> Iterator[str]:
    """Session-scoped localstack container per CLAUDE.md."""
    with LocalStackContainer(image="localstack/localstack:3") as ls:
        ls.with_services("s3")
        yield ls.get_url()


@pytest.fixture(scope="session")
def s3_client(localstack_endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=TEST_REGION,
    )


@pytest.fixture(scope="session")
def seeded_bucket(s3_client) -> str:
    """Create bucket + upload fixture manifest, specs, bom.yaml, plate spec."""
    s3_client.create_bucket(Bucket=BUCKET)

    manifest = {
        "version": "0.1.0-test",
        "specs": {
            "CMP-NODE-001": f"s3://{BUCKET}/equipment/CMP-NODE-001/spec.yaml",
            "CMP-RACK-001": f"s3://{BUCKET}/equipment/CMP-RACK-001/spec.yaml",
        },
        "geometry": {},
        "assemblies": {
            "compute_container": {
                "commercial-ac": {
                    "bom": f"s3://{BUCKET}/assemblies/compute-container/commercial-ac/bom.yaml",
                    "step": f"s3://{BUCKET}/assemblies/compute-container/commercial-ac/assembly.step",
                    "glb": f"s3://{BUCKET}/assemblies/compute-container/commercial-ac/assembly.glb",
                    "topology_yaml": f"s3://{BUCKET}/assemblies/compute-container/commercial-ac/topology.yaml",
                }
            }
        },
        "plates": {
            "CG": {
                "spec": f"s3://{BUCKET}/plates/CG/v1/spec.yaml",
                "step": f"s3://{BUCKET}/plates/CG/v1/plate.step",
            }
        },
        "profiles": {
            "commercial_ac": {
                "compute_container": "commercial-ac",
                "grid_container": None,
                "interface_plates": ["CG"],
            }
        },
    }
    s3_client.put_object(
        Bucket=BUCKET, Key="manifest.yaml", Body=yaml.safe_dump(manifest)
    )

    s3_client.put_object(
        Bucket=BUCKET,
        Key="equipment/CMP-NODE-001/spec.yaml",
        Body=yaml.safe_dump(
            {
                "equipment_id": "CMP-NODE-001",
                "model_number": "SYS-421GE-NBRT-LCC",
                "vendor": "Supermicro",
                "description": "4U HGX B200 server",
                "datasheet_url": "https://example.com/datasheet.pdf",
                "lead_time_weeks": 4,
                "fab_tier": "dod_eligible",
            }
        ),
    )
    s3_client.put_object(
        Bucket=BUCKET,
        Key="equipment/CMP-RACK-001/spec.yaml",
        Body=yaml.safe_dump(
            {
                "equipment_id": "CMP-RACK-001",
                "model_number": "AR9658",
                "vendor": "Schneider",
                "description": "52U NetShelter SX",
                "fab_tier": "dod_eligible",
            }
        ),
    )

    s3_client.put_object(
        Bucket=BUCKET,
        Key="assemblies/compute-container/commercial-ac/bom.yaml",
        Body=yaml.safe_dump(
            {
                "parts": [
                    {"equipment_id": "CMP-NODE-001", "qty": 7},
                    {"equipment_id": "CMP-RACK-001", "qty": 1},
                ],
                "plates": [{"id": "CG", "version": "v1", "qty": 1}],
            }
        ),
    )

    # topology.yaml for DTM — new canonical shape (template + connection)
    s3_client.put_object(
        Bucket=BUCKET,
        Key="assemblies/compute-container/commercial-ac/topology.yaml",
        Body=yaml.safe_dump(
            {
                "devices": [
                    {
                        "template": "gpu_node",
                        "description": "HGX B200 #1",
                        "connection": {
                            "host": "mock-redfish-server",
                            "port": 8443,
                        },
                    }
                ],
                "buses": [],
            }
        ),
    )

    s3_client.put_object(
        Bucket=BUCKET,
        Key="plates/CG/v1/spec.yaml",
        Body=yaml.safe_dump(
            {
                "plate_id": "CG",
                "description": "Interface Plate, Compute-to-Grid",
                "deployment_contexts": {
                    "commercial": {
                        "material": "6061-T6 aluminum (ASTM B209)",
                        "finish": "Type II anodize 15-25 μm",
                    }
                },
            }
        ),
    )
    return BUCKET


def test_bom_generator_against_localstack(
    monkeypatch, localstack_endpoint: str, seeded_bucket: str
) -> None:
    # arrange — point manifest_client at localstack
    monkeypatch.setenv("S3_ENDPOINT_URL", localstack_endpoint)
    client = ManifestClient(manifest_url=f"s3://{seeded_bucket}/manifest.yaml")
    service = BomGeneratorService(client)

    # act
    bom = service.generate(deployment_id=uuid4(), profile="commercial_ac")

    # assert — Q9-C success criterion
    line_pn = {li.part_number: li for li in bom.line_items}
    assert "SYS-421GE-NBRT-LCC" in line_pn
    assert line_pn["SYS-421GE-NBRT-LCC"].qty == 7
    assert "ARC-PLT-CG-001" in line_pn
    assert (
        line_pn["ARC-PLT-CG-001"].procurement_path == ProcurementPath.CUSTOM_FABRICATION
    )
    assert line_pn["ARC-PLT-CG-001"].material == "6061-T6 aluminum (ASTM B209)"
    assert bom.manifest_version == "0.1.0-test"


def test_upload_bom_json_to_localstack(
    monkeypatch, localstack_endpoint: str, seeded_bucket: str, s3_client
) -> None:
    # arrange
    monkeypatch.setenv("S3_ENDPOINT_URL", localstack_endpoint)
    client = ManifestClient(manifest_url=f"s3://{seeded_bucket}/manifest.yaml")
    service = BomGeneratorService(client)
    bom = service.generate(deployment_id=uuid4(), profile="commercial_ac")
    target_url = f"s3://{seeded_bucket}/edp/{bom.deployment_id}/bom.json"

    # act
    client.upload_bom_json(serialize_bom(bom), target_url)

    # assert — fetch back from localstack
    key = target_url.removeprefix(f"s3://{seeded_bucket}/")
    body = s3_client.get_object(Bucket=seeded_bucket, Key=key)["Body"].read()
    import json

    fetched = json.loads(body)
    assert fetched["profile"] == "commercial_ac"
    assert any(li["part_number"] == "ARC-PLT-CG-001" for li in fetched["line_items"])


def test_dtm_generator_against_localstack(
    monkeypatch, localstack_endpoint: str, seeded_bucket: str
) -> None:
    """dtm_generator fetches manifest + topology.yaml from S3 (canonical Dtm shape).

    Same manifest pipeline as bom_generator, second consumer per ADR-006.
    """
    from pathlib import Path

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
    from src.shared.schemas.template import TemplateKind

    # arrange
    monkeypatch.setenv("S3_ENDPOINT_URL", localstack_endpoint)
    client = ManifestClient(manifest_url=f"s3://{seeded_bucket}/manifest.yaml")
    repo_root = Path(__file__).resolve().parents[1]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    service = DtmGeneratorService(client, template_catalog=catalog)
    resolution = ModuleResolution(
        deployment_id=uuid4(),
        deployment_profile=DeploymentProfile.COMMERCIAL_AC,
        compute_container_count=2,
        grid_container_present=False,  # fixture has no grid
        bess_coupling=BessCoupling.NONE,
        bess_capacity_mwh=0.0,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=GpuVariant.B200,
        gpu_count=14,
        climate_zone=ClimateZone.TEMPERATE,
    )

    # act
    dtm = service.generate(profile="commercial_ac", resolution=resolution)

    # assert — Q9-C-equivalent for DTM (canonical Dtm shape)
    assert dtm.ems_mode == EmsMode.SIM
    # 2 compute_module devices (one per container), no grid
    module_devices = [
        d
        for d in dtm.devices.values()
        if dtm.templates_used[d.template].kind == TemplateKind.MODULE
    ]
    assert len(module_devices) == 2
    # 2 leaf gpu_node devices (1 per topology x 2 containers)
    gpu_devices = [d for d in dtm.devices.values() if d.template == "gpu_node"]
    assert len(gpu_devices) == 2
    # verify gpu_node is in templates_used and is a leaf
    assert "gpu_node" in dtm.templates_used
    assert dtm.templates_used["gpu_node"].kind == TemplateKind.LEAF

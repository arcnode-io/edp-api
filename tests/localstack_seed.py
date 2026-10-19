"""Fixture manifest, specs, bom.yaml and plate spec for the localstack S3 tests."""

import yaml
from botocore.client import BaseClient

BUCKET = "arcnode-artifacts"


def seed_bucket(s3_client: BaseClient) -> str:
    """Create the bucket and upload the fixture catalog; returns the bucket."""
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
                "shell": {"part_number": "ARC-CNT-CMP-001", "description": "shell"},
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

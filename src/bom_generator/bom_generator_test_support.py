"""Manifest and client builders for BOM generator tests; import explicitly."""

from unittest.mock import MagicMock


from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)


def _make_manifest() -> Manifest:
    """Minimal manifest for commercial_ac with one compute container + CG plate."""
    return Manifest(
        version="0.1.0",
        specs={
            "CMP-NODE-001": "s3://test/equipment/CMP-NODE-001/spec.yaml",
            "CMP-RACK-001": "s3://test/equipment/CMP-RACK-001/spec.yaml",
        },
        assemblies={
            "compute_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/assemblies/compute-container/commercial-ac/bom.yaml",
                    step="s3://test/assemblies/compute-container/commercial-ac/assembly.step",
                    glb="s3://test/assemblies/compute-container/commercial-ac/assembly.glb",
                )
            }
        },
        plates={
            "CG": PlateUrls(
                spec="s3://test/plates/CG/v1/spec.yaml",
                step="s3://test/plates/CG/v1/plate.step",
            )
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container=None,  # Reason: skip grid for unit-test simplicity
                interface_plates=["CG"],
            )
        },
    )


def _make_mock_client(manifest: Manifest) -> MagicMock:
    client = MagicMock()
    client.fetch_manifest.return_value = manifest
    client.fetch_bom_yaml.return_value = {
        "shell": {"part_number": "ARC-CNT-CMP-001", "description": "Compute shell"},
        "parts": [
            {"equipment_id": "CMP-NODE-001", "qty": 7},
            {"equipment_id": "CMP-RACK-001", "qty": 1},
        ],
        "plates": [{"id": "CG", "version": "v1", "qty": 1}],
    }

    def fake_fetch_spec(url: str) -> dict:
        if "CMP-NODE-001" in url:
            return {
                "equipment_id": "CMP-NODE-001",
                "model_number": "SYS-421GE-NBRT-LCC",
                "vendor": "Supermicro",
                "description": "4U HGX B200 server",
                "datasheet_url": "https://example.com/datasheet.pdf",
                "lead_time_weeks": 4,
                "fab_tier": "dod_eligible",  # → TAA-compliant (derived)
                "restricted_entities": None,  # → NDAA-compliant (derived)
                "install_video_url": "https://youtu.be/abc123",
            }
        if "CMP-RACK-001" in url:
            return {
                "equipment_id": "CMP-RACK-001",
                "model_number": "AR9658",
                "vendor": "Schneider",
                "description": "52U NetShelter SX",
                "fab_tier": "commercial",  # → TAA unverified (derived False)
                "restricted_entities": None,
            }
        if "CG" in url:
            return {
                "plate_id": "CG",
                "description": "Interface Plate, Compute-to-Grid",
                "deployment_contexts": {
                    "commercial": {
                        "material": "6061-T6 aluminum",
                        "finish": "Type II anodize",
                    }
                },
            }
        raise ValueError(f"unmocked spec: {url}")

    client.fetch_spec.side_effect = fake_fetch_spec
    return client

"""BomGeneratorService grid lines: one primary grid container plus feeders."""

from unittest.mock import MagicMock
from uuid import uuid4

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    ProfileAssemblies,
)

_GRID_PARTS = ("GRD-XFM-001", "GRD-SWG-001", "GRD-RLY-001", "GRD-MTR-001")


def _variant(name: str) -> AssemblyVariant:
    return AssemblyVariant(
        bom=f"s3://test/{name}/bom.yaml",
        step=f"s3://test/{name}/assembly.step",
        glb=f"s3://test/{name}/assembly.glb",
    )


def _manifest() -> Manifest:
    return Manifest(
        version="0.1.0",
        specs={eid: f"s3://test/equipment/{eid}/spec.yaml" for eid in _GRID_PARTS},
        assemblies={
            "compute_container": {"commercial-ac": _variant("compute")},
            "grid_container": {
                "commercial-ac": _variant("grid"),
                "feeder": _variant("feeder"),
            },
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                grid_feeder_container="feeder",
            )
        },
    )


def _client(manifest: Manifest) -> MagicMock:
    boms = {
        "s3://test/compute/bom.yaml": {"parts": []},
        "s3://test/grid/bom.yaml": {
            "parts": [{"equipment_id": eid, "qty": 1} for eid in _GRID_PARTS]
        },
        # Feeder = primary minus the POI meter
        "s3://test/feeder/bom.yaml": {
            "parts": [{"equipment_id": eid, "qty": 1} for eid in _GRID_PARTS[:3]]
        },
    }
    client = MagicMock()
    client.fetch_manifest.return_value = manifest
    client.fetch_bom_yaml.side_effect = boms.__getitem__
    client.fetch_spec.side_effect = lambda url: {
        "equipment_id": url.split("/")[-2],
        "model_number": url.split("/")[-2],
    }
    return client


def test_three_grid_containers_are_one_primary_and_two_feeders() -> None:
    # Arrange
    service = BomGeneratorService(_client(_manifest()))

    # Act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        compute_container_qty=1,
        grid_container_qty=3,
    )

    # Assert — one line per part; only the primary carries the POI meter
    actual = {li.part_number: li.qty for li in bom.line_items}
    expected = {"GRD-XFM-001": 3, "GRD-SWG-001": 3, "GRD-RLY-001": 3, "GRD-MTR-001": 1}
    assert actual == expected

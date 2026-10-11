"""BomGeneratorService grid lines: one primary grid container plus feeders."""

from unittest.mock import MagicMock
from uuid import uuid4

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.bom_models import ProcurementPath
from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)

_GRID_PARTS = ("GRD-XFM-001", "GRD-SWG-001", "GRD-RLY-001", "GRD-MTR-001")
_PLATES = ("CG", "CD", "BG-AC")


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
        plates={
            pid: PlateUrls(
                spec=f"s3://test/plates/{pid}/spec.yaml",
                step=f"s3://test/plates/{pid}/plate.step",
            )
            for pid in _PLATES
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                grid_feeder_container="feeder",
                interface_plates=list(_PLATES),
            )
        },
    )


def _plates(*ids: str) -> list[dict]:
    return [{"id": pid, "version": "v1", "qty": 1} for pid in ids]


def _shell(part_number: str) -> dict:
    return {"part_number": part_number, "description": f"{part_number} shell"}


def _client(manifest: Manifest) -> MagicMock:
    boms = {
        "s3://test/compute/bom.yaml": {
            "shell": _shell("ARC-CNT-CMP-001"),
            "parts": [],
            "plates": _plates("CG", "CD"),
        },
        "s3://test/grid/bom.yaml": {
            "shell": _shell("ARC-CNT-GRD-001"),
            "parts": [{"equipment_id": eid, "qty": 1} for eid in _GRID_PARTS],
            "plates": _plates("CG", "BG-AC"),
        },
        # Feeder = primary minus the POI meter, and no BESS plate
        "s3://test/feeder/bom.yaml": {
            "shell": _shell("ARC-CNT-GRD-001"),
            "parts": [{"equipment_id": eid, "qty": 1} for eid in _GRID_PARTS[:3]],
            "plates": _plates("CG"),
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
    actual = {
        li.part_number: li.qty
        for li in bom.line_items
        if li.part_number.startswith("GRD")
    }
    expected = {"GRD-XFM-001": 3, "GRD-SWG-001": 3, "GRD-RLY-001": 3, "GRD-MTR-001": 1}
    assert actual == expected


def test_every_container_brings_its_own_interface_plates() -> None:
    # Arrange
    service = BomGeneratorService(_client(_manifest()))

    # Act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        compute_container_qty=2,
        grid_container_qty=3,
    )

    # Assert — CG on all 5 containers, CD per compute, BG-AC on the primary only
    actual = {
        li.part_number: li.qty
        for li in bom.line_items
        if li.part_number.startswith("ARC-PLT")
    }
    expected = {"ARC-PLT-CG-001": 5, "ARC-PLT-CD-001": 2, "ARC-PLT-BG-AC-001": 1}
    assert actual == expected


def test_every_container_ships_in_its_own_shell() -> None:
    # Arrange
    service = BomGeneratorService(_client(_manifest()))

    # Act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        compute_container_qty=2,
        grid_container_qty=3,
    )

    # Assert — built to order, one per container
    shells = [li for li in bom.line_items if li.part_number.startswith("ARC-CNT")]
    actual = {li.part_number: (li.qty, li.procurement_path) for li in shells}
    expected = {
        "ARC-CNT-CMP-001": (2, ProcurementPath.CUSTOM_FABRICATION),
        "ARC-CNT-GRD-001": (3, ProcurementPath.CUSTOM_FABRICATION),
    }
    assert actual == expected

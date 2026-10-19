"""Unit tests for BomGeneratorService — fully mocked S3."""

from uuid import uuid4

import pytest

from src.bom_generator.bom_test_support import ORDER
from src.shared.enums import GpuVariant
from src.bom_generator.bom_generator_service import (
    BomGeneratorService,
    serialize_bom,
)
from src.bom_generator.bom_models import ProcurementPath
from src.bom_generator.bom_generator_test_support import (
    _make_manifest,
    _make_mock_client,
)


def test_generate_returns_bom_with_compute_lines() -> None:
    # arrange
    manifest = _make_manifest()
    client = _make_mock_client(manifest)
    service = BomGeneratorService(client)
    deployment_id = uuid4()
    # act
    actual = service.generate(
        deployment_id=deployment_id,
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )
    # assert
    assert actual.profile == "commercial_ac"
    assert actual.manifest_version == "0.1.0"
    line_pn = {li.part_number for li in actual.line_items}
    assert "SYS-421GE-NBRT-LCC" in line_pn
    assert "AR9658" in line_pn


def test_generate_multiplies_qty_by_container_count() -> None:
    # arrange
    client = _make_mock_client(_make_manifest())
    service = BomGeneratorService(client)
    expected_node_qty = 7 * 3  # 7 nodes per container x 3 containers
    # act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
        compute_container_qty=3,
    )
    # assert
    nodes = next(li for li in bom.line_items if li.part_number == "SYS-421GE-NBRT-LCC")
    assert nodes.qty == expected_node_qty


def test_generate_includes_cg_plate_as_custom_fabrication() -> None:
    # arrange
    client = _make_mock_client(_make_manifest())
    service = BomGeneratorService(client)
    # act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )
    # assert
    plate = next(li for li in bom.line_items if li.part_number == "ARC-PLT-CG-001")
    assert plate.procurement_path == ProcurementPath.CUSTOM_FABRICATION
    assert plate.material == "6061-T6 aluminum"
    assert plate.vendor == "CNC shop, to ARCNODE drawing"


def test_generate_defense_plate_appends_d_suffix() -> None:
    # arrange
    client = _make_mock_client(_make_manifest())
    # add defense_forward to plate spec
    original_side = client.fetch_spec.side_effect

    def with_defense(url: str) -> dict:
        spec = original_side(url)
        if url.endswith("plates/CG/v1/spec.yaml"):
            spec["deployment_contexts"]["defense_forward"] = {
                "material": "5083-H116",
                "finish": "Type III hard anodize",
            }
        return spec

    client.fetch_spec.side_effect = with_defense
    service = BomGeneratorService(client)
    # act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
        deployment_context="defense_forward",
    )
    # assert
    plate = next(li for li in bom.line_items if li.part_number.startswith("ARC-PLT-CG"))
    assert plate.part_number.endswith("-D")
    assert plate.material == "5083-H116"


def test_generate_raises_for_unknown_profile() -> None:
    # arrange
    client = _make_mock_client(_make_manifest())
    service = BomGeneratorService(client)
    # act / assert
    with pytest.raises(ValueError, match="defense_dc_int"):
        service.generate(
            deployment_id=uuid4(),
            profile="defense_dc_int",
            gpu_variant=GpuVariant.B200,
            order=ORDER,
        )


def test_serialize_bom_emits_valid_json() -> None:
    # arrange
    client = _make_mock_client(_make_manifest())
    service = BomGeneratorService(client)
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )
    # act
    actual = serialize_bom(bom)
    # assert
    import json

    parsed = json.loads(actual)
    assert parsed["profile"] == "commercial_ac"
    assert isinstance(parsed["line_items"], list)

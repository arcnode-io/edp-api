"""Catalog lines carry the spec's install video and NDAA/TAA status."""

from uuid import uuid4


from src.bom_generator.bom_test_support import ORDER
from src.shared.enums import GpuVariant
from src.bom_generator.bom_generator_service import (
    BomGeneratorService,
)
from src.bom_generator.bom_generator_test_support import (
    _make_manifest,
    _make_mock_client,
)


def test_catalog_line_surfaces_install_video_url_from_spec() -> None:
    """spec.install_video_url surfaces into the catalog line item."""
    # Arrange
    client = _make_mock_client(_make_manifest())
    service = BomGeneratorService(client)

    # Act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )

    # Assert
    node_line = next(
        li for li in bom.line_items if li.part_number == "SYS-421GE-NBRT-LCC"
    )
    assert node_line.install_video_url == "https://youtu.be/abc123"


def test_catalog_line_derives_ndaa_from_restricted_entities() -> None:
    """NDAA compliance: True iff `NDAA_889` not in `restricted_entities`.

    The schema already tracks NDAA Section 889 via the `restricted_entities`
    enum. Adding a separate `ndaa_compliant` field on the spec would
    duplicate + risk drift. Generator derives instead.
    """
    # Arrange
    client = _make_mock_client(_make_manifest())
    service = BomGeneratorService(client)

    # Act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )

    # Assert — both fixtures have restricted_entities=None → NDAA True for both
    node_line = next(
        li for li in bom.line_items if li.part_number == "SYS-421GE-NBRT-LCC"
    )
    rack_line = next(li for li in bom.line_items if li.part_number == "AR9658")
    assert node_line.ndaa_compliant is True
    assert rack_line.ndaa_compliant is True


def test_catalog_line_derives_taa_from_fab_tier() -> None:
    """TAA compliance: True iff fab_tier is federal_civilian or dod_eligible.

    Federal procurement requires TAA compliance, so federally-procurable
    equipment is TAA-compliant by definition. `commercial` fab_tier
    doesn't claim either way → derived False (= unverified).
    """
    # Arrange
    client = _make_mock_client(_make_manifest())
    service = BomGeneratorService(client)

    # Act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )

    # Assert
    node_line = next(
        li for li in bom.line_items if li.part_number == "SYS-421GE-NBRT-LCC"
    )
    rack_line = next(li for li in bom.line_items if li.part_number == "AR9658")
    assert node_line.taa_compliant is True  # fab_tier=dod_eligible
    assert rack_line.taa_compliant is False  # fab_tier=commercial — unverified


def test_ndaa_false_when_restricted_entities_lists_889() -> None:
    """A spec with NDAA_889 in restricted_entities renders ndaa_compliant=False."""
    # Arrange
    manifest = _make_manifest()
    client = _make_mock_client(manifest)
    original = client.fetch_spec.side_effect

    def with_ndaa_restriction(url: str) -> dict:
        spec = original(url)
        if "CMP-NODE-001" in url:
            spec["restricted_entities"] = ["NDAA_889"]
        return spec

    client.fetch_spec.side_effect = with_ndaa_restriction
    service = BomGeneratorService(client)

    # Act
    bom = service.generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )

    # Assert
    node_line = next(
        li for li in bom.line_items if li.part_number == "SYS-421GE-NBRT-LCC"
    )
    assert node_line.ndaa_compliant is False

"""artifact_urls unit tests."""

from pathlib import Path
from uuid import UUID

from src.hardware_selector.hardware_selector_service import HardwareSelectorService
from src.pipeline.artifact_urls import build_artifact_urls
from src.shared.enums import DeploymentProfile
from src.shared.schemas.artifact import ArtifactKind

YAML_PATH: Path = Path(__file__).resolve().parents[2] / "hardware_selector_map.yaml"
DEPLOYMENT_ID: UUID = UUID("11111111-2222-3333-4444-555555555555")


def test_commercial_ac_produces_28_urls() -> None:
    """commercial_ac: 2 compute + 2 grid + 5 plates x 3 fmts + 13 generated = 32."""
    # Arrange
    selector = HardwareSelectorService(yaml_path=YAML_PATH)
    assemblies = selector.lookup(DeploymentProfile.COMMERCIAL_AC)

    # Act
    actual = build_artifact_urls(DEPLOYMENT_ID, assemblies)

    # Assert
    assert len(actual) == 2 + 2 + 5 * 3 + 13


def test_no_bess_omits_grid_container() -> None:
    """commercial_no_bess: no grid_container slot, 4 plates x 3 = 12 plate refs."""
    # Arrange
    selector = HardwareSelectorService(yaml_path=YAML_PATH)
    assemblies = selector.lookup(DeploymentProfile.COMMERCIAL_NO_BESS)

    # Act
    actual = build_artifact_urls(DEPLOYMENT_ID, assemblies)

    # Assert
    grid_refs = [r for r in actual if r.kind == ArtifactKind.GRID_CONTAINER_3D]
    assert grid_refs == []
    plate_refs = [r for r in actual if r.kind == ArtifactKind.INTERFACE_PLATE]
    assert len(plate_refs) == 4 * 3


def test_generated_urls_use_deterministic_key_scheme() -> None:
    """All generated artifacts under s3://arcnode-artifacts/edp/{deployment_id}/..."""
    # Arrange
    selector = HardwareSelectorService(yaml_path=YAML_PATH)
    assemblies = selector.lookup(DeploymentProfile.COMMERCIAL_AC)
    expected_prefix = f"s3://arcnode-artifacts/edp/{DEPLOYMENT_ID}/"

    # Act
    actual = build_artifact_urls(DEPLOYMENT_ID, assemblies)

    # Assert
    bom_json = next(
        r for r in actual if r.kind == ArtifactKind.BOM and r.format == "json"
    )
    assert bom_json.url == f"{expected_prefix}bom.json"
    dtm = next(r for r in actual if r.kind == ArtifactKind.DTM)
    assert dtm.url == f"{expected_prefix}dtm.json"


def test_plates_carry_plate_id_only() -> None:
    """Only INTERFACE_PLATE refs carry plate_id; others are None."""
    # Arrange
    selector = HardwareSelectorService(yaml_path=YAML_PATH)
    assemblies = selector.lookup(DeploymentProfile.COMMERCIAL_AC)

    # Act
    actual = build_artifact_urls(DEPLOYMENT_ID, assemblies)

    # Assert
    for r in actual:
        if r.kind == ArtifactKind.INTERFACE_PLATE:
            assert r.plate_id is not None
        else:
            assert r.plate_id is None

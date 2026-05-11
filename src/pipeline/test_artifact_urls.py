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


# ─── Regression: legacy vs manifest path equivalence ──────────────────


def test_legacy_and_manifest_paths_agree_on_commercial_ac_artifact_shape() -> None:
    """Both paths produce: 2 compute + 2 grid + 13 generated = 17 non-plate refs.

    Plate refs differ on purpose — legacy yaml ships step+dxf+pdf per plate
    (3 per id), new manifest ships step+dxf when dxf present (≤2 per id).
    Same plate-id set, same generated set, same compute/grid URLs → swap-safe.

    Locks in the swap contract before JobsService starts depending on the
    new path. Manifest fixture is hand-built to mirror the commercial_ac
    profile in edp-module-assemblies/manifest.yaml.
    """
    from src.bom_generator.manifest_models import (
        AssemblyVariant,
        Manifest,
        PlateUrls,
        ProfileAssemblies,
    )
    from src.bom_generator.manifest_service import ManifestService
    from src.pipeline.artifact_urls import build_artifact_urls_from_resolved

    # Arrange — legacy path
    legacy_assemblies = HardwareSelectorService(yaml_path=YAML_PATH).lookup(
        DeploymentProfile.COMMERCIAL_AC
    )

    # Arrange — manifest path with the same SHAPE for commercial_ac
    manifest = Manifest(
        version="0.0.0-regression-test",
        assemblies={
            "compute_container": {
                "commercial-ac": AssemblyVariant(
                    bom=legacy_assemblies.compute_container.step.replace(
                        "/assembly.step", "/bom.yaml"
                    ),
                    step=legacy_assemblies.compute_container.step,
                    glb=legacy_assemblies.compute_container.glb,
                ),
            },
            "grid_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/grid/commercial-ac/bom.yaml",
                    step=legacy_assemblies.grid_container.step,  # type: ignore[union-attr]
                    glb=legacy_assemblies.grid_container.glb,  # type: ignore[union-attr]
                ),
            },
        },
        plates={
            p.id: PlateUrls(
                spec=f"s3://test/plates/{p.id}/spec.yaml",
                step=p.step,
                dxf=p.dxf,
            )
            for p in legacy_assemblies.interface_plates
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=[p.id for p in legacy_assemblies.interface_plates],
            ),
        },
    )
    resolved = ManifestService(manifest=manifest).resolve("commercial_ac")

    # Act
    legacy_refs = build_artifact_urls(DEPLOYMENT_ID, legacy_assemblies)
    new_refs = build_artifact_urls_from_resolved(DEPLOYMENT_ID, resolved)

    # Assert — non-plate refs identical
    legacy_non_plate = [r for r in legacy_refs if r.kind != ArtifactKind.INTERFACE_PLATE]
    new_non_plate = [r for r in new_refs if r.kind != ArtifactKind.INTERFACE_PLATE]
    assert legacy_non_plate == new_non_plate, "compute/grid/generated URLs must match"

    # Assert — plate id sets identical
    legacy_plate_ids = {
        r.plate_id for r in legacy_refs if r.kind == ArtifactKind.INTERFACE_PLATE
    }
    new_plate_ids = {
        r.plate_id for r in new_refs if r.kind == ArtifactKind.INTERFACE_PLATE
    }
    assert legacy_plate_ids == new_plate_ids

    # Assert — per-plate format expectations: legacy has 3 (step,dxf,pdf),
    # new has 2 (step,dxf) per documented schema diff.
    for pid in legacy_plate_ids:
        legacy_fmts = {
            r.format
            for r in legacy_refs
            if r.kind == ArtifactKind.INTERFACE_PLATE and r.plate_id == pid
        }
        new_fmts = {
            r.format
            for r in new_refs
            if r.kind == ArtifactKind.INTERFACE_PLATE and r.plate_id == pid
        }
        assert legacy_fmts == {"step", "dxf", "pdf"}
        assert new_fmts == {"step", "dxf"}, (
            f"plate {pid}: new path drops pdf — confirmed migration intent"
        )

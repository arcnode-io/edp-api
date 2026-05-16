"""artifact_urls unit tests — manifest-backed (in-memory fixture, no I/O)."""

from uuid import UUID

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.bom_generator.manifest_service import ManifestService
from src.pipeline.artifact_urls import build_artifact_urls_from_resolved
from src.shared.schemas.artifact import ArtifactKind

DEPLOYMENT_ID: UUID = UUID("11111111-2222-3333-4444-555555555555")


def _variant(name: str) -> AssemblyVariant:
    return AssemblyVariant(
        bom=f"s3://test/{name}/bom.yaml",
        step=f"s3://test/{name}/assembly.step",
        glb=f"s3://test/{name}/assembly.glb",
    )


def _plate(name: str, *, with_dxf: bool = True) -> PlateUrls:
    return PlateUrls(
        spec=f"s3://test/plates/{name}/spec.yaml",
        step=f"s3://test/plates/{name}/{name}.step",
        dxf=f"s3://test/plates/{name}/{name}.dxf" if with_dxf else None,
    )


def _commercial_ac_manifest() -> Manifest:
    """Mirrors edp-module-assemblies/manifest.yaml commercial_ac shape."""
    return Manifest(
        version="0.0.0-test",
        assemblies={
            "compute_container": {"commercial-ac": _variant("compute-commercial-ac")},
            "grid_container": {"commercial-ac": _variant("grid-commercial-ac")},
        },
        plates={
            "CG": _plate("CG"),
            "BG-AC": _plate("BG-AC"),
            "CD": _plate("CD"),
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "BG-AC", "CD"],
            ),
        },
    )


def _commercial_no_bess_manifest() -> Manifest:
    """Profile with no grid_container; one plate."""
    m = _commercial_ac_manifest()
    m.profiles["commercial_no_bess"] = ProfileAssemblies(
        compute_container="commercial-ac",
        grid_container=None,
        interface_plates=["CG"],
    )
    return m


def test_commercial_ac_produces_expected_ref_count() -> None:
    """commercial_ac: 2 compute + 2 grid + 3 plates x 2 fmts (step+dxf) + 14 generated = 24."""
    # Arrange
    svc = ManifestService(manifest=_commercial_ac_manifest())
    resolved = svc.resolve("commercial_ac")

    # Act
    refs = build_artifact_urls_from_resolved(DEPLOYMENT_ID, resolved)

    # Assert
    assert len(refs) == 2 + 2 + 3 * 2 + 14


def test_commercial_no_bess_omits_grid_container() -> None:
    """commercial_no_bess profile: zero GRID_CONTAINER_3D refs in the output."""
    # Arrange
    svc = ManifestService(manifest=_commercial_no_bess_manifest())
    resolved = svc.resolve("commercial_no_bess")

    # Act
    refs = build_artifact_urls_from_resolved(DEPLOYMENT_ID, resolved)

    # Assert
    grid_refs = [r for r in refs if r.kind == ArtifactKind.GRID_CONTAINER_3D]
    assert grid_refs == []


def test_generated_urls_use_deterministic_key_scheme() -> None:
    """All generated artifacts under s3://arcnode-artifacts/edp/{deployment_id}/..."""
    # Arrange
    svc = ManifestService(manifest=_commercial_ac_manifest())
    resolved = svc.resolve("commercial_ac")
    expected_prefix = f"s3://arcnode-artifacts/edp/{DEPLOYMENT_ID}/"

    # Act
    refs = build_artifact_urls_from_resolved(DEPLOYMENT_ID, resolved)

    # Assert — spot-check BOM + DTM keys
    bom_json = next(
        r for r in refs if r.kind == ArtifactKind.BOM and r.format == "json"
    )
    assert bom_json.url == f"{expected_prefix}bom.json"
    dtm = next(r for r in refs if r.kind == ArtifactKind.DTM)
    assert dtm.url == f"{expected_prefix}dtm.json"


def test_plates_carry_plate_id_only() -> None:
    """Only INTERFACE_PLATE refs carry plate_id; others are None."""
    # Arrange
    svc = ManifestService(manifest=_commercial_ac_manifest())
    resolved = svc.resolve("commercial_ac")

    # Act
    refs = build_artifact_urls_from_resolved(DEPLOYMENT_ID, resolved)

    # Assert
    for r in refs:
        if r.kind == ArtifactKind.INTERFACE_PLATE:
            assert r.plate_id is not None
        else:
            assert r.plate_id is None


def test_plate_without_dxf_emits_only_step() -> None:
    """Optional manifest.plates[*].dxf — when None, only the step ref ships."""
    # Arrange
    manifest = _commercial_ac_manifest()
    manifest.plates["NO-DXF"] = _plate("NO-DXF", with_dxf=False)
    manifest.profiles["commercial_ac"] = ProfileAssemblies(
        compute_container="commercial-ac",
        grid_container="commercial-ac",
        interface_plates=["NO-DXF"],
    )
    resolved = ManifestService(manifest=manifest).resolve("commercial_ac")

    # Act
    refs = build_artifact_urls_from_resolved(DEPLOYMENT_ID, resolved)

    # Assert — exactly one INTERFACE_PLATE ref, format=step
    plate_refs = [r for r in refs if r.kind == ArtifactKind.INTERFACE_PLATE]
    assert len(plate_refs) == 1
    assert plate_refs[0].format == "step"
    assert plate_refs[0].plate_id == "NO-DXF"

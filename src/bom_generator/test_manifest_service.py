"""ManifestService unit tests — in-memory Manifest fixture, no I/O."""

import pytest

from src.shared.enums import GpuVariant

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.bom_generator.manifest_service import (
    ManifestService,
    ResolvedPlate,
    ResolvedProfile,
)


def _variant(name: str) -> AssemblyVariant:
    """Minimal AssemblyVariant for fixtures."""
    return AssemblyVariant(
        bom=f"s3://test/{name}/bom.yaml",
        step=f"s3://test/{name}/assembly.step",
        glb=f"s3://test/{name}/assembly.glb",
    )


def _plate(name: str) -> PlateUrls:
    return PlateUrls(
        spec=f"s3://test/plates/{name}/spec.yaml",
        step=f"s3://test/plates/{name}/{name}.step",
        dxf=f"s3://test/plates/{name}/{name}.dxf",
    )


def _manifest_fixture() -> Manifest:
    """Hand-built Manifest mirroring the edp-module-assemblies schema."""
    return Manifest(
        version="0.0.0-test",
        assemblies={
            "compute_container": {
                "commercial-ac": _variant("compute-commercial-ac"),
                "defense-ac": _variant("compute-defense-ac"),
                "commercial-ac-h100": _variant("compute-commercial-ac-h100"),
            },
            "grid_container": {
                "commercial-ac": _variant("grid-commercial-ac"),
                "no-bess": _variant("grid-no-bess"),
            },
        },
        plates={
            "CG": _plate("CG"),
            "CD": _plate("CD"),
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                compute_container_by_gpu={
                    GpuVariant.B200: "commercial-ac",
                    GpuVariant.H100_SXM: "commercial-ac-h100",
                },
                grid_container="commercial-ac",
                interface_plates=["CG", "CD"],
            ),
            "defense_ac": ProfileAssemblies(
                compute_container="defense-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "CD"],
            ),
            "bad_grid_ref": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="does-not-exist",
                interface_plates=["CG"],
            ),
        },
    )


def test_resolve_returns_resolved_profile_for_known_profile() -> None:
    """commercial_ac lookup returns a fully-resolved bundle."""
    # Arrange
    svc = ManifestService(manifest=_manifest_fixture())

    # Act
    resolved = svc.resolve("commercial_ac", gpu_variant=GpuVariant.B200)

    # Assert — type + content
    assert isinstance(resolved, ResolvedProfile)
    assert resolved.compute.step.endswith("/compute-commercial-ac/assembly.step")
    assert resolved.grid is not None
    assert resolved.grid.step.endswith("/grid-commercial-ac/assembly.step")
    assert [p.plate_id for p in resolved.plates] == ["CG", "CD"]


def test_resolve_no_grid_when_profile_grid_container_is_none() -> None:
    """A profile with grid_container=None resolves with grid=None — no lookup."""
    # Arrange
    manifest = _manifest_fixture()
    manifest.profiles["truly_no_bess"] = ProfileAssemblies(
        compute_container="commercial-ac",
        grid_container=None,
        interface_plates=["CG"],
    )
    svc = ManifestService(manifest=manifest)

    # Act
    resolved = svc.resolve("truly_no_bess", gpu_variant=GpuVariant.B200)

    # Assert
    assert resolved.grid is None


def test_resolve_plates_keep_plate_id_attached() -> None:
    """Plate IDs survive resolution so artifact_urls can label INTERFACE_PLATE refs."""
    # Arrange
    svc = ManifestService(manifest=_manifest_fixture())

    # Act
    resolved = svc.resolve("commercial_ac", gpu_variant=GpuVariant.B200)

    # Assert
    plates_by_id = {p.plate_id: p for p in resolved.plates}
    assert "CD" in plates_by_id
    assert isinstance(plates_by_id["CD"], ResolvedPlate)
    assert plates_by_id["CD"].urls.dxf is not None


def test_resolve_unknown_profile_raises_key_error() -> None:
    """Unknown profile fails fast — fail at intake, not at artifact emit."""
    # Arrange
    svc = ManifestService(manifest=_manifest_fixture())

    # Act / Assert
    with pytest.raises(KeyError):
        svc.resolve("not_a_profile", gpu_variant=GpuVariant.B200)


def test_resolve_dangling_grid_reference_raises_key_error() -> None:
    """A profile pointing at a missing assembly variant fails fast (catalog drift)."""
    # Arrange
    svc = ManifestService(manifest=_manifest_fixture())

    # Act / Assert
    with pytest.raises(KeyError):
        svc.resolve("bad_grid_ref", gpu_variant=GpuVariant.B200)


def test_the_ordered_gpu_picks_the_compute_container() -> None:
    # Arrange — an H100 order must get H100 nodes, not the B200 container
    svc = ManifestService(manifest=_manifest_fixture())

    # Act
    resolved = svc.resolve("commercial_ac", gpu_variant=GpuVariant.H100_SXM)

    # Assert
    assert resolved.compute.step.endswith("/compute-commercial-ac-h100/assembly.step")

"""ManifestService unit tests — in-memory Manifest fixture, no I/O."""

from typing import cast

import pytest

from src.bom_generator.manifest_client import ManifestClient
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
            },
            "grid_container": {
                "commercial-ac": _variant("grid-commercial-ac"),
                "no-bess": _variant("grid-no-bess"),
            },
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
            "commercial_no_bess": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="no-bess",
                interface_plates=["CG", "CD"],
            ),
            "defense_ac": ProfileAssemblies(
                compute_container="defense-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "BG-AC", "CD"],
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
    resolved = svc.resolve("commercial_ac")

    # Assert — type + content
    assert isinstance(resolved, ResolvedProfile)
    assert resolved.compute.step.endswith("/compute-commercial-ac/assembly.step")
    assert resolved.grid is not None
    assert resolved.grid.step.endswith("/grid-commercial-ac/assembly.step")
    assert [p.plate_id for p in resolved.plates] == ["CG", "BG-AC", "CD"]


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
    resolved = svc.resolve("truly_no_bess")

    # Assert
    assert resolved.grid is None


def test_resolve_plates_keep_plate_id_attached() -> None:
    """Plate IDs survive resolution so artifact_urls can label INTERFACE_PLATE refs."""
    # Arrange
    svc = ManifestService(manifest=_manifest_fixture())

    # Act
    resolved = svc.resolve("commercial_ac")

    # Assert
    plates_by_id = {p.plate_id: p for p in resolved.plates}
    assert "BG-AC" in plates_by_id
    assert isinstance(plates_by_id["BG-AC"], ResolvedPlate)
    assert plates_by_id["BG-AC"].urls.dxf is not None


def test_resolve_unknown_profile_raises_key_error() -> None:
    """Unknown profile fails fast — fail at intake, not at artifact emit."""
    # Arrange
    svc = ManifestService(manifest=_manifest_fixture())

    # Act / Assert
    with pytest.raises(KeyError):
        svc.resolve("not_a_profile")


def test_resolve_dangling_grid_reference_raises_key_error() -> None:
    """A profile pointing at a missing assembly variant fails fast (catalog drift)."""
    # Arrange
    svc = ManifestService(manifest=_manifest_fixture())

    # Act / Assert
    with pytest.raises(KeyError):
        svc.resolve("bad_grid_ref")


def test_from_client_fetches_once() -> None:
    """ManifestService.from_client calls client.fetch_manifest exactly once."""
    # Arrange
    manifest = _manifest_fixture()
    fetch_count = 0

    class _StubClient:
        def fetch_manifest(self) -> Manifest:
            nonlocal fetch_count
            fetch_count += 1
            return manifest

    # Act — _StubClient duck-types ManifestClient (only fetch_manifest used).
    svc = ManifestService.from_client(cast(ManifestClient, _StubClient()))
    svc.resolve("commercial_ac")
    svc.resolve("commercial_no_bess")
    svc.resolve("defense_ac")

    # Assert — three lookups, one fetch
    assert fetch_count == 1

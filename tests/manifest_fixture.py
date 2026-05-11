"""Shared in-memory ManifestModule fixture for tests that boot AppModule.

AppModule's default ManifestModule fetches manifest.yaml from S3 at startup.
Tests that don't need a real manifest pass `commercial_ac_manifest_module()`
into `AppModule(manifest_module_override=...)` to skip the fetch entirely.

Covers the commercial_ac profile only — sufficient for healthcheck +
configurator-payload integration tests. Wider coverage lives in the
service-level test fixtures.
"""

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.bom_generator.manifest_module import ManifestModule


def commercial_ac_manifest_module() -> ManifestModule:
    """ManifestModule loaded with a hand-built commercial_ac-only Manifest."""
    return ManifestModule.from_manifest(_commercial_ac_manifest())


def _commercial_ac_manifest() -> Manifest:
    return Manifest(
        version="0.0.0-test",
        assemblies={
            "compute_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/compute/commercial-ac/bom.yaml",
                    step="s3://test/compute/commercial-ac/assembly.step",
                    glb="s3://test/compute/commercial-ac/assembly.glb",
                ),
            },
            "grid_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/grid/commercial-ac/bom.yaml",
                    step="s3://test/grid/commercial-ac/assembly.step",
                    glb="s3://test/grid/commercial-ac/assembly.glb",
                ),
            },
        },
        plates={
            "CG": PlateUrls(
                spec="s3://test/plates/CG/spec.yaml",
                step="s3://test/plates/CG/CG.step",
                dxf="s3://test/plates/CG/CG.dxf",
            ),
            "BG-AC": PlateUrls(
                spec="s3://test/plates/BG-AC/spec.yaml",
                step="s3://test/plates/BG-AC/BG-AC.step",
                dxf="s3://test/plates/BG-AC/BG-AC.dxf",
            ),
            "CD": PlateUrls(
                spec="s3://test/plates/CD/spec.yaml",
                step="s3://test/plates/CD/CD.step",
                dxf="s3://test/plates/CD/CD.dxf",
            ),
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "BG-AC", "CD"],
            ),
        },
    )

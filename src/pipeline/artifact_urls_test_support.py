"""Manifest builders for artifact URL tests; import explicitly."""

from uuid import UUID


from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)

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

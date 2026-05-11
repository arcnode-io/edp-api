"""Build the deterministic ArtifactRef[] list for a deployment.

Two parallel paths during the hardware_selector → manifest migration:
- `build_artifact_urls(deployment_id, ProfileAssemblies)` — legacy, sourced
  from hardware_selector_map.yaml (deprecated; will be removed).
- `build_artifact_urls_from_resolved(deployment_id, ResolvedProfile)` — new,
  sourced from the edp-module-assemblies manifest via ManifestService.

Both produce the same set of "generated" deterministic-key refs (BOM, SLD,
etc. under `edp/{deployment_id}/`). They differ slightly on plate refs:
the manifest schema has step + optional dxf and no pdf for plates, while
the legacy yaml had step + dxf + pdf. PDF for plates is dropped in the
new path; if needed, generate it downstream as a pipeline artifact.
"""

from uuid import UUID

from src.bom_generator.manifest_models import AssemblyVariant
from src.bom_generator.manifest_service import ResolvedPlate, ResolvedProfile
from src.hardware_selector.hardware_selector_models import (
    AssemblyUrls,
    PlateUrls,
    ProfileAssemblies,
)
from src.shared.schemas.artifact import ArtifactKind, ArtifactRef

_BUCKET = "arcnode-artifacts"


def build_artifact_urls(
    deployment_id: UUID, assemblies: ProfileAssemblies
) -> list[ArtifactRef]:
    """Combine selected (yaml) + generated (deterministic) URLs into one flat list."""
    refs: list[ArtifactRef] = []
    refs.extend(_compute_container(assemblies.compute_container))
    if assemblies.grid_container is not None:
        refs.extend(_grid_container(assemblies.grid_container))
    refs.extend(_interface_plates(assemblies.interface_plates))
    refs.extend(_generated(deployment_id))
    return refs


def _compute_container(urls: AssemblyUrls) -> list[ArtifactRef]:
    return [
        ArtifactRef(
            kind=ArtifactKind.COMPUTE_CONTAINER_3D, format="step", url=urls.step
        ),
        ArtifactRef(kind=ArtifactKind.COMPUTE_CONTAINER_3D, format="glb", url=urls.glb),
    ]


def _grid_container(urls: AssemblyUrls) -> list[ArtifactRef]:
    return [
        ArtifactRef(kind=ArtifactKind.GRID_CONTAINER_3D, format="step", url=urls.step),
        ArtifactRef(kind=ArtifactKind.GRID_CONTAINER_3D, format="glb", url=urls.glb),
    ]


def _interface_plates(plates: list[PlateUrls]) -> list[ArtifactRef]:
    refs: list[ArtifactRef] = []
    for p in plates:
        refs.extend(
            [
                ArtifactRef(
                    kind=ArtifactKind.INTERFACE_PLATE,
                    format="step",
                    url=p.step,
                    plate_id=p.id,
                ),
                ArtifactRef(
                    kind=ArtifactKind.INTERFACE_PLATE,
                    format="dxf",
                    url=p.dxf,
                    plate_id=p.id,
                ),
                ArtifactRef(
                    kind=ArtifactKind.INTERFACE_PLATE,
                    format="pdf",
                    url=p.pdf,
                    plate_id=p.id,
                ),
            ]
        )
    return refs


def _generated(deployment_id: UUID) -> list[ArtifactRef]:
    """Deterministic s3 keys for everything edp-api will produce."""
    base = f"s3://{_BUCKET}/edp/{deployment_id}"
    pairs: list[tuple[ArtifactKind, str, str]] = [
        (ArtifactKind.BOM, "json", f"{base}/bom.json"),
        (ArtifactKind.BOM, "xlsx", f"{base}/bom.xlsx"),
        (ArtifactKind.SLD, "dxf", f"{base}/sld.dxf"),
        (ArtifactKind.SLD, "pdf", f"{base}/sld.pdf"),
        (ArtifactKind.PID_COOLING, "dxf", f"{base}/pid_cooling.dxf"),
        (ArtifactKind.PID_COOLING, "pdf", f"{base}/pid_cooling.pdf"),
        (ArtifactKind.COMMS_DIAGRAM, "dxf", f"{base}/comms.dxf"),
        (ArtifactKind.COMMS_DIAGRAM, "pdf", f"{base}/comms.pdf"),
        (ArtifactKind.CABLE_HOSE_SCHEDULE, "json", f"{base}/cable_hose_schedule.json"),
        (ArtifactKind.CABLE_HOSE_SCHEDULE, "xlsx", f"{base}/cable_hose_schedule.xlsx"),
        (ArtifactKind.INSTALLATION_GRAPH, "dxf", f"{base}/installation_graph.dxf"),
        (ArtifactKind.INSTALLATION_GRAPH, "pdf", f"{base}/installation_graph.pdf"),
        (ArtifactKind.DTM, "json", f"{base}/dtm.json"),
    ]
    return [ArtifactRef(kind=k, format=fmt, url=u) for k, fmt, u in pairs]


# ─── New manifest-based path ───────────────────────────────────────────


def build_artifact_urls_from_resolved(
    deployment_id: UUID, resolved: ResolvedProfile
) -> list[ArtifactRef]:
    """Same shape as `build_artifact_urls`, but sourced from the new manifest.

    Plate refs differ from the legacy path: the manifest schema has step +
    optional dxf and no pdf for plates, so this fn emits step always, dxf
    only if the manifest provides it, and never pdf for plates. Generated
    refs are identical.
    """
    refs: list[ArtifactRef] = []
    refs.extend(_compute_container_resolved(resolved.compute))
    if resolved.grid is not None:
        refs.extend(_grid_container_resolved(resolved.grid))
    refs.extend(_interface_plates_resolved(resolved.plates))
    refs.extend(_generated(deployment_id))
    return refs


def _compute_container_resolved(variant: AssemblyVariant) -> list[ArtifactRef]:
    return [
        ArtifactRef(
            kind=ArtifactKind.COMPUTE_CONTAINER_3D, format="step", url=variant.step
        ),
        ArtifactRef(
            kind=ArtifactKind.COMPUTE_CONTAINER_3D, format="glb", url=variant.glb
        ),
    ]


def _grid_container_resolved(variant: AssemblyVariant) -> list[ArtifactRef]:
    return [
        ArtifactRef(
            kind=ArtifactKind.GRID_CONTAINER_3D, format="step", url=variant.step
        ),
        ArtifactRef(
            kind=ArtifactKind.GRID_CONTAINER_3D, format="glb", url=variant.glb
        ),
    ]


def _interface_plates_resolved(plates: list[ResolvedPlate]) -> list[ArtifactRef]:
    """Step (always) + dxf (when manifest provides). PDF dropped per new schema."""
    refs: list[ArtifactRef] = []
    for p in plates:
        refs.append(
            ArtifactRef(
                kind=ArtifactKind.INTERFACE_PLATE,
                format="step",
                url=p.urls.step,
                plate_id=p.plate_id,
            )
        )
        if p.urls.dxf is not None:
            refs.append(
                ArtifactRef(
                    kind=ArtifactKind.INTERFACE_PLATE,
                    format="dxf",
                    url=p.urls.dxf,
                    plate_id=p.plate_id,
                )
            )
    return refs

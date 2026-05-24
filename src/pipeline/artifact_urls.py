"""Build the deterministic ArtifactRef[] list for a deployment.

Pure fn: (deployment_id, ResolvedProfile) -> list[ArtifactRef].
Mixes selected URLs (from the edp-module-assemblies manifest, resolved by
ManifestService) with generated URLs (deterministic s3 keys under
edp/{deployment_id}/...).

Plate refs: step (always) + dxf (when the manifest provides it). PDF for
plates is not in the new manifest schema; if needed, generate it as a
pipeline output under the deterministic key scheme.
"""

from uuid import UUID

from src.bom_generator.manifest_models import AssemblyVariant
from src.bom_generator.manifest_service import ResolvedPlate, ResolvedProfile
from src.shared.schemas.artifact import ArtifactKind, ArtifactRef

_BUCKET = "arcnode-artifacts"


def build_artifact_urls_from_resolved(
    deployment_id: UUID, resolved: ResolvedProfile
) -> list[ArtifactRef]:
    """Combine selected (manifest) + generated (deterministic) URLs into one flat list."""
    refs: list[ArtifactRef] = []
    refs.extend(_compute_container(resolved.compute))
    if resolved.grid is not None:
        refs.extend(_grid_container(resolved.grid))
    refs.extend(_interface_plates(resolved.plates))
    refs.extend(_generated(deployment_id))
    return refs


def _compute_container(variant: AssemblyVariant) -> list[ArtifactRef]:
    return [
        ArtifactRef(
            kind=ArtifactKind.COMPUTE_CONTAINER_3D, format="step", url=variant.step
        ),
        ArtifactRef(
            kind=ArtifactKind.COMPUTE_CONTAINER_3D, format="glb", url=variant.glb
        ),
    ]


def _grid_container(variant: AssemblyVariant) -> list[ArtifactRef]:
    return [
        ArtifactRef(
            kind=ArtifactKind.GRID_CONTAINER_3D, format="step", url=variant.step
        ),
        ArtifactRef(kind=ArtifactKind.GRID_CONTAINER_3D, format="glb", url=variant.glb),
    ]


def _interface_plates(plates: list[ResolvedPlate]) -> list[ArtifactRef]:
    """Step always + dxf when manifest provides. PDF dropped per new schema."""
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


def _generated(deployment_id: UUID) -> list[ArtifactRef]:
    """Deterministic s3 keys for everything edp-api will produce."""
    base = f"s3://{_BUCKET}/edp/{deployment_id}"
    pairs: list[tuple[ArtifactKind, str, str]] = [
        (ArtifactKind.BOM, "json", f"{base}/bom.json"),
        (ArtifactKind.BOM, "xlsx", f"{base}/bom.xlsx"),
        (ArtifactKind.SLD, "dxf", f"{base}/sld.dxf"),
        (ArtifactKind.SLD, "pdf", f"{base}/sld.pdf"),
        (ArtifactKind.SLD_HMI_SVG, "svg", f"{base}/sld_hmi.svg"),
        (ArtifactKind.PID_COOLING, "dxf", f"{base}/pid_cooling.dxf"),
        (ArtifactKind.PID_COOLING, "pdf", f"{base}/pid_cooling.pdf"),
        (ArtifactKind.COMMS_DIAGRAM, "dxf", f"{base}/comms.dxf"),
        (ArtifactKind.COMMS_DIAGRAM, "pdf", f"{base}/comms.pdf"),
        (ArtifactKind.CABLE_HOSE_SCHEDULE, "json", f"{base}/cable_hose_schedule.json"),
        (ArtifactKind.CABLE_HOSE_SCHEDULE, "xlsx", f"{base}/cable_hose_schedule.xlsx"),
        (ArtifactKind.INSTALL_SEQUENCE, "pdf", f"{base}/install_sequence.pdf"),
        (ArtifactKind.DTM, "json", f"{base}/dtm.json"),
    ]
    return [ArtifactRef(kind=k, format=fmt, url=u) for k, fmt, u in pairs]

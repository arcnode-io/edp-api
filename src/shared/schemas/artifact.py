"""Artifact response shapes — single source of truth for the GET/POST contracts."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class JobStatus(StrEnum):
    """Job lifecycle states."""

    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class ArtifactKind(StrEnum):
    """One slot per artifact category. INTERFACE_PLATE multiplexes by `plate_id`."""

    BOM = "bom"
    COMPUTE_CONTAINER_3D = "compute_container_3d"
    GRID_CONTAINER_3D = "grid_container_3d"
    INTERFACE_PLATE = "interface_plate"
    SLD = "sld"
    SLD_HMI_SVG = "sld_hmi_svg"
    PID_COOLING = "pid_cooling"
    COMMS_DIAGRAM = "comms_diagram"
    CABLE_HOSE_SCHEDULE = "cable_hose_schedule"
    INSTALL_SEQUENCE = "install_sequence"
    DTM = "dtm"


class ArtifactSummary(BaseModel):
    """Real counts for one artifact, shown next to its download.

    Only the fields for the ref's kind are set: bom → line_items + vendors,
    cable_hose_schedule → runs + media_kinds, dtm → devices + buses,
    interface_plate → plates (qty of that plate_id; kinds = distinct plate_ids).
    """

    line_items: int | None = None
    vendors: int | None = None
    runs: int | None = None
    media_kinds: int | None = None
    devices: int | None = None
    buses: int | None = None
    plates: int | None = None


class ArtifactRef(BaseModel):
    """One artifact entry — flat shape, one per (kind, format[, plate_id])."""

    kind: ArtifactKind
    format: str  # json | xlsx | dxf | pdf | step | glb
    url: str
    plate_id: str | None = None  # only when kind=INTERFACE_PLATE
    # None until the job is COMPLETE (counts only exist after generation), and
    # always None for kinds without counts.
    summary: ArtifactSummary | None = None


class JobCreated(BaseModel):
    """edp-api POST /edp-api/jobs 202 body. URLs known up front (deterministic keys)."""

    job_id: UUID
    status_url: str
    edp_artifact_urls: list[ArtifactRef]


class JobResult(BaseModel):
    """edp-api GET /edp-api/jobs/{id} body."""

    status: JobStatus
    edp_artifact_urls: list[ArtifactRef]
    error: str | None = None  # set when status=FAILED

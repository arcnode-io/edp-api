"""In-memory record for one job. Lives only inside `JobStore`."""

from uuid import UUID

from pydantic import BaseModel

from src.bom_generator.manifest_models import Manifest
from src.shared.schemas.artifact import ArtifactRef, JobStatus
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.module_resolution import ModuleResolution


class JobRecord(BaseModel):
    """One row in the in-memory JobStore.

    `payload` + `resolution` are kept on the record so the BackgroundTask
    pipeline can resume from the record alone (no extra round-trip through
    ModuleResolverService). `manifest` is pinned at create() time so the
    pipeline sees the same hardware contract the 202 response was built
    against (closes ADR-012 torn-read). All three are stripped from the
    public JobResult projection — clients see status + URLs only.
    """

    job_id: UUID
    status: JobStatus
    edp_artifact_urls: list[ArtifactRef]
    payload: ConfiguratorPayload
    resolution: ModuleResolution
    manifest: Manifest
    error: str | None = None

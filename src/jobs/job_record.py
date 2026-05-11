"""In-memory record for one job. Lives only inside `JobStore`."""

from uuid import UUID

from pydantic import BaseModel

from src.shared.schemas.artifact import ArtifactRef, JobStatus
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.module_resolution import ModuleResolution


class JobRecord(BaseModel):
    """One row in the in-memory JobStore.

    `payload` + `resolution` are kept on the record so the BackgroundTask
    pipeline can resume from the record alone (no extra round-trip through
    ModuleResolverService). They're stripped from the public JobResult
    projection — clients see status + URLs only.
    """

    job_id: UUID
    status: JobStatus
    edp_artifact_urls: list[ArtifactRef]
    payload: ConfiguratorPayload
    resolution: ModuleResolution
    error: str | None = None

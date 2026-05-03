"""In-memory record for one job. Lives only inside `JobStore`."""

from uuid import UUID

from pydantic import BaseModel

from src.shared.schemas.artifact import ArtifactRef, JobStatus


class JobRecord(BaseModel):
    """One row in the in-memory JobStore."""

    job_id: UUID
    status: JobStatus
    edp_artifact_urls: list[ArtifactRef]
    error: str | None = None

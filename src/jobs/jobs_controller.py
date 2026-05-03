"""Jobs HTTP controller — POST /edp-api/jobs + GET /edp-api/jobs/{id}."""

from uuid import UUID

from classy_fastapi import Routable, get, post
from fastapi import HTTPException, status

from src.jobs.jobs_service import JobsService
from src.shared.schemas.artifact import JobCreated, JobResult
from src.shared.schemas.configurator_payload import ConfiguratorPayload


class JobsController(Routable):
    """REST surface for the EDP job lifecycle."""

    def __init__(self, service: JobsService) -> None:
        super().__init__()
        self._service = service

    @post(
        "/edp-api/jobs",
        response_model=JobCreated,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["Jobs"],
    )
    async def create(self, payload: ConfiguratorPayload) -> JobCreated:
        """Submit a configurator payload; receive deterministic URLs + job_id."""
        return self._service.create(payload)

    @get(
        "/edp-api/jobs/{job_id}",
        response_model=JobResult,
        tags=["Jobs"],
    )
    async def get(self, job_id: UUID) -> JobResult:
        """Fetch current status of a job. 404 if unknown."""
        result = self._service.get(job_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"job {job_id} not found",
            )
        return result

"""JobsService — creates jobs, runs the pipeline, queries state.

`create` returns the 202 body synchronously (resolves the profile, computes
deterministic URLs, stores RUNNING). The caller (JobsController) schedules
`execute` as a FastAPI BackgroundTask which runs PipelineService and flips
status to COMPLETE on success / FAILED on exception.
"""

import logging
from uuid import UUID, uuid4

from src.bom_generator.manifest_service import ManifestService
from src.jobs.job_record import JobRecord
from src.jobs.job_store import JobStore
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.pipeline.artifact_urls import build_artifact_urls_from_resolved
from src.pipeline.pipeline_service import PipelineService
from src.shared.schemas.artifact import JobCreated, JobResult, JobStatus
from src.shared.schemas.configurator_payload import ConfiguratorPayload

logger = logging.getLogger(__name__)


class JobsService:
    """Creates jobs, runs them, serves their state."""

    def __init__(
        self,
        *,
        resolver: ModuleResolverService,
        manifest: ManifestService,
        pipeline: PipelineService,
        store: JobStore,
    ) -> None:
        self._resolver = resolver
        self._manifest = manifest
        self._pipeline = pipeline
        self._store = store

    def create(self, payload: ConfiguratorPayload) -> JobCreated:
        """Resolve, build URLs, store as RUNNING, return the 202 body."""
        resolution = self._resolver.resolve(payload)
        resolved = self._manifest.resolve(resolution.deployment_profile.value)
        urls = build_artifact_urls_from_resolved(payload.deployment_id, resolved)
        job_id = uuid4()
        self._store.put(
            JobRecord(
                job_id=job_id,
                status=JobStatus.RUNNING,
                edp_artifact_urls=urls,
                payload=payload,
                resolution=resolution,
            )
        )
        return JobCreated(
            job_id=job_id,
            status_url=f"/edp-api/jobs/{job_id}",
            edp_artifact_urls=urls,
        )

    def execute(self, job_id: UUID) -> None:
        """Run the per-deployment artifact pipeline. Flips status terminal."""
        record = self._store.get(job_id)
        if record is None:
            logger.error("execute called for unknown job %s", job_id)
            return
        try:
            self._pipeline.run(
                payload=record.payload,
                resolution=record.resolution,
                urls=record.edp_artifact_urls,
            )
        except Exception as e:
            logger.exception("pipeline failed for job %s", job_id)
            self._store.put(
                record.model_copy(update={"status": JobStatus.FAILED, "error": str(e)})
            )
            return
        self._store.put(record.model_copy(update={"status": JobStatus.COMPLETE}))
        logger.info("job %s complete", job_id)

    def get(self, job_id: UUID) -> JobResult | None:
        """Project a JobRecord onto the public JobResult shape, or None if missing."""
        record = self._store.get(job_id)
        if record is None:
            return None
        return JobResult(
            status=record.status,
            edp_artifact_urls=record.edp_artifact_urls,
            error=record.error,
        )

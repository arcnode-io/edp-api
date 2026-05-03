"""JobsService — creates jobs and queries their state.

Composes ModuleResolverService + HardwareSelectorService + artifact_urls to
produce the up-front URL list returned in the 202. The actual artifact bytes
are written by the pipeline (FastAPI BackgroundTask) — not yet wired.
"""

from uuid import UUID, uuid4

from src.hardware_selector.hardware_selector_service import HardwareSelectorService
from src.jobs.job_record import JobRecord
from src.jobs.job_store import JobStore
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.pipeline.artifact_urls import build_artifact_urls
from src.shared.schemas.artifact import JobCreated, JobResult, JobStatus
from src.shared.schemas.configurator_payload import ConfiguratorPayload


class JobsService:
    """Creates jobs and serves their state."""

    def __init__(
        self,
        *,
        resolver: ModuleResolverService,
        selector: HardwareSelectorService,
        store: JobStore,
    ) -> None:
        self._resolver = resolver
        self._selector = selector
        self._store = store

    def create(self, payload: ConfiguratorPayload) -> JobCreated:
        """Resolve, build URLs, store as RUNNING, return the 202 body."""
        resolution = self._resolver.resolve(payload)
        assemblies = self._selector.lookup(resolution.deployment_profile)
        urls = build_artifact_urls(payload.deployment_id, assemblies)
        job_id = uuid4()
        self._store.put(
            JobRecord(job_id=job_id, status=JobStatus.RUNNING, edp_artifact_urls=urls)
        )
        return JobCreated(
            job_id=job_id,
            status_url=f"/edp-api/jobs/{job_id}",
            edp_artifact_urls=urls,
        )

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

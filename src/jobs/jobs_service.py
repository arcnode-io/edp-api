"""JobsService — creates jobs, runs the pipeline, queries state.

`create` returns the 202 body synchronously: fetches the manifest from S3,
resolves the profile against it, computes deterministic URLs, pins the
manifest on the JobRecord, and stores RUNNING. The caller (JobsController)
then schedules `execute` as a FastAPI BackgroundTask which runs
PipelineService using the pinned manifest and flips status to COMPLETE on
success / FAILED on exception.

Manifest is fetched per-job (not at app startup) and pinned for the job's
lifetime — closes ADR-011 torn-read between resolve and DTM emit.
"""

import logging
from uuid import UUID, uuid4

from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_service import ManifestService
from src.grid.region_validation import validate_against_regions
from src.jobs.job_record import JobRecord
from src.jobs.job_store import JobStore
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.pipeline.artifact_urls import build_artifact_urls_from_resolved
from src.pipeline.pipeline_service import PipelineService
from src.shared.enums import GridPath
from src.shared.schemas.artifact import JobCreated, JobResult, JobStatus
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.grid_regions import GridRegionsConfig
from src.shared.schemas.sizing import SizingGridInput, SizingPreviewRequest
from src.sizing.sizing_service import SizingService

logger = logging.getLogger(__name__)


def _sizing_request(payload: ConfiguratorPayload) -> SizingPreviewRequest:
    """Project ConfiguratorPayload onto the narrower sizing-preview shape."""
    grid = payload.grid
    return SizingPreviewRequest(
        gpu_variant=payload.gpu_variant,
        target_gpu_count=payload.target_gpu_count,
        bess_coupling=payload.bess_coupling,
        bess_capacity_mwh=payload.bess_capacity_mwh,
        ride_through_hours=payload.ride_through_hours,
        deployment_context=payload.deployment_context,
        onsite_generation=payload.onsite_generation,
        grid=SizingGridInput(
            path=grid.path,
            market_region=grid.market_region,
            service_type=grid.service_type,
            flex_obligation=grid.flex_obligation,
            export_mode=grid.export_mode,
            intentional_islanding=grid.intentional_islanding,
        ),
    )


class JobsService:
    """Creates jobs, runs them, serves their state."""

    def __init__(
        self,
        *,
        resolver: ModuleResolverService,
        client: ManifestClient,
        pipeline: PipelineService,
        store: JobStore,
        regions: GridRegionsConfig,
        sizing: SizingService,
    ) -> None:
        self._resolver = resolver
        self._client = client
        self._pipeline = pipeline
        self._store = store
        self._regions = regions
        self._sizing = sizing

    def create(self, payload: ConfiguratorPayload) -> JobCreated:
        """Validate, size, resolve, build URLs, store as RUNNING.

        Raises ValueError on the first region-dependent rule violation
        (V4b/V6/SP/FL) — the controller maps that to a 422, same as pydantic's
        own structural validators.
        """
        validate_against_regions(payload, self._regions)
        preview = self._sizing.preview(_sizing_request(payload))
        # IL: interconnection_level is server-derived — overwrite whatever the
        # client sent with the preview's computed value. off_grid is exempt:
        # V1 requires interconnection_level null there, and a would-be level
        # (still computed for the site-peak math) doesn't apply to a site
        # that isn't interconnecting at all.
        if payload.grid.path != GridPath.OFF_GRID:
            payload = payload.model_copy(
                update={
                    "grid": payload.grid.model_copy(
                        update={"interconnection_level": preview.interconnection_level}
                    )
                }
            )
        resolution = self._resolver.resolve(payload)
        manifest = self._client.fetch_manifest()
        resolved = ManifestService(manifest=manifest).resolve(
            resolution.deployment_profile.value
        )
        urls = build_artifact_urls_from_resolved(payload.deployment_id, resolved)
        job_id = uuid4()
        self._store.put(
            JobRecord(
                job_id=job_id,
                status=JobStatus.RUNNING,
                edp_artifact_urls=urls,
                payload=payload,
                resolution=resolution,
                manifest=manifest,
                sizing_preview=preview,
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
                manifest=record.manifest,
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

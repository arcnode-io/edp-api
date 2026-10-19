"""JobsService unit tests — manifest-backed (in-memory fixture, no I/O)."""

from uuid import UUID

import pytest

from src.jobs.job_store import JobStore
from src.jobs.jobs_service import JobsService
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    GpuVariant,
    GridPath,
    OnsiteGenerationType,
    PrimaryWorkload,
)
from src.shared.schemas.artifact import ArtifactSummary, JobStatus
from src.shared.schemas.configurator_grid import (
    Grid,
    OnsiteGeneration,
    Site,
    SiteLocation,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.sizing.sizing_service import SizingService
from src.jobs.jobs_test_support import (
    DEPLOYMENT_ID,
    _commercial_ac_manifest,
    _NullPipeline,
    _StaticClient,
    _regions,
    _CapturingPipeline,
    _MutatingClient,
    _alternate_manifest,
    _CountingPipeline,
)


@pytest.fixture
def service() -> JobsService:
    """Real resolver + in-memory manifest client + null pipeline + fresh store."""
    return JobsService(
        resolver=ModuleResolverService(),
        client=_StaticClient(
            _commercial_ac_manifest()
        ),  # ty: ignore[invalid-argument-type]
        pipeline=_NullPipeline(),  # ty: ignore[invalid-argument-type]
        store=JobStore(),
        regions=_regions(),
        sizing=SizingService(regions=_regions()),
    )


@pytest.fixture
def payload() -> ConfiguratorPayload:
    """Commercial AC happy-path payload."""
    return ConfiguratorPayload(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=56,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=DeploymentContext.COMMERCIAL,
        aws_partition=AwsPartition.STANDARD,
        site=Site(location=SiteLocation(lat=32.7, lon=-96.8), country="US"),
        onsite_generation=OnsiteGeneration(type=OnsiteGenerationType.NONE),
        grid=Grid(path=GridPath.OFF_GRID),
    )


def test_create_returns_202_body_with_urls(
    service: JobsService, payload: ConfiguratorPayload
) -> None:
    """create() returns JobCreated with deterministic URL list."""
    # Act
    actual = service.create(payload)

    # Assert
    assert actual.status_url == f"/edp-api/jobs/{actual.job_id}"
    assert len(actual.edp_artifact_urls) > 0


def test_create_starts_job_in_running_state(
    service: JobsService, payload: ConfiguratorPayload
) -> None:
    """Newly-created job is queryable + RUNNING."""
    # Act
    created = service.create(payload)
    actual = service.get(created.job_id)

    # Assert
    assert actual is not None
    assert actual.status == JobStatus.RUNNING


def test_get_missing_returns_none(service: JobsService) -> None:
    """Unknown job_id returns None, not raises."""
    # Act
    actual = service.get(UUID("00000000-0000-0000-0000-000000000099"))

    # Assert
    assert actual is None


def test_create_url_list_matches_artifact_url_builder(
    service: JobsService, payload: ConfiguratorPayload
) -> None:
    """JobCreated.edp_artifact_urls matches the JobRecord.edp_artifact_urls."""
    # Act
    created = service.create(payload)
    fetched = service.get(created.job_id)

    # Assert
    assert fetched is not None
    assert created.edp_artifact_urls == fetched.edp_artifact_urls


def test_execute_uses_manifest_pinned_at_create_not_re_fetched(
    payload: ConfiguratorPayload,
) -> None:
    """Manifest fetched at create() flows pinned through to pipeline.run().

    Closes ADR-011 torn-read: if the manifest source mutates between POST
    and pipeline execution, the pipeline still sees what create() saw.
    """
    # Arrange
    original_manifest = _commercial_ac_manifest()
    client = _MutatingClient(current=original_manifest)
    capturing = _CapturingPipeline()
    service = JobsService(
        resolver=ModuleResolverService(),
        client=client,  # ty: ignore[invalid-argument-type]
        pipeline=capturing,  # ty: ignore[invalid-argument-type]
        store=JobStore(),
        regions=_regions(),
        sizing=SizingService(regions=_regions()),
    )

    # Act — create, mutate the source, then execute
    created = service.create(payload)
    client.current = _alternate_manifest()  # simulate mid-flight manifest change
    service.execute(created.job_id)

    # Assert — pipeline saw the original (pinned at create), not the mutation
    assert capturing.last_call is not None
    assert capturing.last_call["manifest"] is original_manifest


def test_completed_job_serves_the_pipelines_counts(
    payload: ConfiguratorPayload,
) -> None:
    """GET after execute shows the counts the pipeline produced."""
    # Arrange
    service = JobsService(
        resolver=ModuleResolverService(),
        client=_StaticClient(
            _commercial_ac_manifest()
        ),  # ty: ignore[invalid-argument-type]
        pipeline=_CountingPipeline(),  # ty: ignore[invalid-argument-type]
        store=JobStore(),
        regions=_regions(),
        sizing=SizingService(regions=_regions()),
    )
    created = service.create(payload)

    # Act
    service.execute(created.job_id)
    actual = service.get(created.job_id)

    # Assert
    assert actual is not None
    assert actual.status == JobStatus.COMPLETE
    assert all(
        r.summary == ArtifactSummary(devices=36, buses=1)
        for r in actual.edp_artifact_urls
    )

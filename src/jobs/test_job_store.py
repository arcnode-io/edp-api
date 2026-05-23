"""JobStore unit tests."""

from uuid import UUID

from src.bom_generator.manifest_models import Manifest
from src.jobs.job_record import JobRecord
from src.jobs.job_store import JobStore
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.enums import (
    AwsPartition,
    WholesaleMarket,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    EnergySource,
    GpuVariant,
    GridConnection,
    PrimaryWorkload,
)
from src.shared.schemas.artifact import JobStatus
from src.shared.schemas.configurator_payload import ConfiguratorPayload

JOB_ID: UUID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000901")


def _record(status: JobStatus = JobStatus.RUNNING) -> JobRecord:
    """Minimal JobRecord — empty url list, real payload + resolution.

    JobRecord now requires payload + resolution so the BackgroundTask
    pipeline has what it needs to resume from the record alone.
    """
    payload = ConfiguratorPayload(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="t",
        contact_email="ops@example.com",
        energy_source=EnergySource.GRID_HYBRID,
        source_capacity_mw=10.0,
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=56,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        grid_connection=GridConnection.GRID_TIED,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=DeploymentContext.COMMERCIAL,
        aws_partition=AwsPartition.STANDARD,
        wholesale_market=WholesaleMarket.ERCOT,
        settlement_point="HB_NORTH",
    )
    resolution = ModuleResolverService().resolve(payload)
    return JobRecord(
        job_id=JOB_ID,
        status=status,
        edp_artifact_urls=[],
        payload=payload,
        resolution=resolution,
        manifest=Manifest(version="0.0.0-test", assemblies={}, plates={}, profiles={}),
    )


def test_get_returns_none_for_missing_job() -> None:
    """Lookup of unknown job returns None."""
    # Arrange
    store = JobStore()

    # Act
    actual = store.get(JOB_ID)

    # Assert
    assert actual is None


def test_put_then_get_roundtrips() -> None:
    """Stored record retrieved verbatim."""
    # Arrange
    store = JobStore()
    record = _record()

    # Act
    store.put(record)
    actual = store.get(JOB_ID)

    # Assert
    assert actual == record


def test_put_overwrites_existing() -> None:
    """Same job_id put twice -> last wins."""
    # Arrange
    store = JobStore()
    initial = _record(JobStatus.RUNNING)
    updated = _record(JobStatus.COMPLETE)

    # Act
    store.put(initial)
    store.put(updated)
    actual = store.get(JOB_ID)

    # Assert
    assert actual is not None
    assert actual.status == JobStatus.COMPLETE

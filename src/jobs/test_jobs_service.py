"""JobsService unit tests — manifest-backed (in-memory fixture, no I/O)."""

from uuid import UUID

import pytest

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.bom_generator.manifest_service import ManifestService
from src.jobs.job_store import JobStore
from src.jobs.jobs_service import JobsService
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.enums import (
    AwsPartition,
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

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000077")


def _commercial_ac_manifest() -> Manifest:
    """Hand-built Manifest covering the commercial_ac profile.

    Sufficient for the test_jobs_service suite, which only exercises the
    commercial_ac happy path. Other profiles aren't needed here — wider
    profile coverage is exercised in test_artifact_urls.py.
    """
    return Manifest(
        version="0.0.0-test",
        assemblies={
            "compute_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/compute/commercial-ac/bom.yaml",
                    step="s3://test/compute/commercial-ac/assembly.step",
                    glb="s3://test/compute/commercial-ac/assembly.glb",
                ),
            },
            "grid_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/grid/commercial-ac/bom.yaml",
                    step="s3://test/grid/commercial-ac/assembly.step",
                    glb="s3://test/grid/commercial-ac/assembly.glb",
                ),
            },
        },
        plates={
            "CG": PlateUrls(
                spec="s3://test/plates/CG/spec.yaml",
                step="s3://test/plates/CG/CG.step",
                dxf="s3://test/plates/CG/CG.dxf",
            ),
            "BG-AC": PlateUrls(
                spec="s3://test/plates/BG-AC/spec.yaml",
                step="s3://test/plates/BG-AC/BG-AC.step",
                dxf="s3://test/plates/BG-AC/BG-AC.dxf",
            ),
            "CD": PlateUrls(
                spec="s3://test/plates/CD/spec.yaml",
                step="s3://test/plates/CD/CD.step",
                dxf="s3://test/plates/CD/CD.dxf",
            ),
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "BG-AC", "CD"],
            ),
        },
    )


@pytest.fixture
def service() -> JobsService:
    """Real resolver + in-memory ManifestService + fresh in-memory store."""
    return JobsService(
        resolver=ModuleResolverService(),
        manifest=ManifestService(manifest=_commercial_ac_manifest()),
        store=JobStore(),
    )


@pytest.fixture
def payload() -> ConfiguratorPayload:
    """Commercial AC happy-path payload."""
    return ConfiguratorPayload(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
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

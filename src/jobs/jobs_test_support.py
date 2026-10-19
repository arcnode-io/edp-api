"""Manifest, client and pipeline doubles for JobsService tests; import explicitly."""

from uuid import UUID


from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.shared.schemas.artifact import ArtifactRef, ArtifactSummary
from src.shared.schemas.grid_regions import GridRegionsConfig, RegionDefaults

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


class _NullPipeline:
    """No-op pipeline for create()/get() tests — execute() isn't exercised here.

    Pipeline behavior is covered by src/pipeline/test_pipeline_service.py;
    this stub keeps JobsService construction tests focused on create/get.
    """

    def run(self, **_: object) -> None:
        return None


class _StaticClient:
    """ManifestClient stub serving a fixed Manifest. No S3."""

    def __init__(self, manifest: Manifest) -> None:
        self._manifest = manifest

    def fetch_manifest(self) -> Manifest:
        return self._manifest


def _regions() -> GridRegionsConfig:
    """Minimal valid config — this suite's off_grid fixture payload never hits
    a region-dependent rule, so the content doesn't matter beyond parsing."""
    return GridRegionsConfig(
        defaults=RegionDefaults(distribution_limit_mw=20, distribution_near_mw=15),
        regions={},
        flex_levels={},
    )


class _CapturingPipeline:
    """Records the kwargs passed to run() so tests can assert what flowed through."""

    def __init__(self) -> None:
        self.last_call: dict[str, object] | None = None

    def run(self, **kwargs: object) -> object:
        self.last_call = kwargs
        return kwargs["urls"]


class _MutatingClient:
    """ManifestClient stub whose fetch_manifest result can change between calls.

    Used to prove JobsService pins the manifest at create() time — pipeline
    execution must see the manifest fetched at create, not whatever the
    client returns later.
    """

    def __init__(self, current: Manifest) -> None:
        self.current = current
        self.fetch_count = 0

    def fetch_manifest(self) -> Manifest:
        self.fetch_count += 1
        return self.current


def _alternate_manifest() -> Manifest:
    """A second manifest that resolves the same commercial_ac profile differently."""
    base = _commercial_ac_manifest()
    return base.model_copy(update={"version": "9.9.9-mutated"})


class _CountingPipeline:
    """Returns the refs with a DTM count attached, like the real pipeline."""

    def run(self, *, urls: list[ArtifactRef], **_: object) -> list[ArtifactRef]:
        return [
            r.model_copy(update={"summary": ArtifactSummary(devices=36, buses=1)})
            for r in urls
        ]

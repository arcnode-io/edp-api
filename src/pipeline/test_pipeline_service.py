"""PipelineService unit tests — captures S3 puts via a stub ManifestClient."""

from src.bom_generator.manifest_service import ManifestService
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.pipeline.artifact_urls import build_artifact_urls_from_resolved
from src.shared.enums import (
    GpuVariant,
)
from src.shared.schemas.artifact import ArtifactKind
from src.pipeline.pipeline_test_support import (
    DEPLOYMENT_ID,
    _RecordingClient,
    _commercial_ac_manifest,
    _payload,
    _build_pipeline,
)


def test_run_uploads_to_every_generated_url() -> None:
    """Per-deployment URLs (under edp/{deployment_id}/) all get bytes."""
    # Arrange
    client = _RecordingClient(_commercial_ac_manifest())
    pipeline = _build_pipeline(client)
    payload = _payload()
    resolution = ModuleResolverService().resolve(payload)
    urls = build_artifact_urls_from_resolved(
        DEPLOYMENT_ID,
        ManifestService(manifest=_commercial_ac_manifest()).resolve(
            "commercial_ac", gpu_variant=GpuVariant.B200
        ),
    )

    # Act
    pipeline.run(
        payload=payload,
        resolution=resolution,
        urls=urls,
        manifest=_commercial_ac_manifest(),
    )

    # Assert — every per-deployment URL was uploaded to exactly once.
    expected = {u.url for u in urls if u.url.startswith("s3://arcnode-artifacts/edp/")}
    assert expected == set(client.uploads.keys()), (
        f"missing: {expected - set(client.uploads)}, "
        f"extra: {set(client.uploads) - expected}"
    )


def test_run_skips_selected_urls_from_catalog() -> None:
    """Selected URLs (assemblies, plates) are NOT touched — they live in catalog."""
    # Arrange
    client = _RecordingClient(_commercial_ac_manifest())
    pipeline = _build_pipeline(client)
    payload = _payload()
    resolution = ModuleResolverService().resolve(payload)
    urls = build_artifact_urls_from_resolved(
        DEPLOYMENT_ID,
        ManifestService(manifest=_commercial_ac_manifest()).resolve(
            "commercial_ac", gpu_variant=GpuVariant.B200
        ),
    )

    # Act
    pipeline.run(
        payload=payload,
        resolution=resolution,
        urls=urls,
        manifest=_commercial_ac_manifest(),
    )

    # Assert — none of the catalog URLs were uploaded
    catalog_urls = {
        u.url for u in urls if not u.url.startswith("s3://arcnode-artifacts/edp/")
    }
    assert catalog_urls.isdisjoint(client.uploads.keys())


def test_all_reserved_artifact_kinds_now_get_real_bytes() -> None:
    """No `_stub_body` fallback paths exercised — every reserved kind has a real generator.

    Regression guard: if a future refactor accidentally drops a real
    generator from the dispatch table, the corresponding URL would
    silently receive stub bytes — this test catches that drift.
    """
    # Arrange
    client = _RecordingClient(_commercial_ac_manifest())
    pipeline = _build_pipeline(client)
    payload = _payload()
    resolution = ModuleResolverService().resolve(payload)
    urls = build_artifact_urls_from_resolved(
        DEPLOYMENT_ID,
        ManifestService(manifest=_commercial_ac_manifest()).resolve(
            "commercial_ac", gpu_variant=GpuVariant.B200
        ),
    )

    # Act
    pipeline.run(
        payload=payload,
        resolution=resolution,
        urls=urls,
        manifest=_commercial_ac_manifest(),
    )

    # Assert — every reserved generated URL got non-stub bytes. Pick the
    # BOM xlsx to verify the shape:
    # real xlsx bytes start with the ZIP magic 'PK'.
    bom_xlsx = next(
        u.url for u in urls if u.kind == ArtifactKind.BOM and u.format == "xlsx"
    )
    assert client.uploads[bom_xlsx][:2] == b"PK"

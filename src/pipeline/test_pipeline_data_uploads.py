"""The pipeline uploads real BOM, DTM and HMI SLD bytes."""

import json

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
    _OneCableSchedule,
)


def test_bom_upload_is_real_bom_json() -> None:
    """The BOM upload deserializes to a Bom shape (not a stub)."""
    # Arrange
    client = _RecordingClient(_commercial_ac_manifest())
    cable_hose = _OneCableSchedule()
    pipeline = _build_pipeline(client, cable_hose=cable_hose)
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

    # Assert
    bom_url = next(
        u.url for u in urls if u.kind == ArtifactKind.BOM and u.format == "json"
    )
    body = json.loads(client.uploads[bom_url])
    assert body["deployment_id"] == str(DEPLOYMENT_ID)
    assert body["profile"] == "commercial_ac"
    # The cable + hose schedule rides along as BOM lines
    lines = {li["part_number"]: li["qty"] for li in body["line_items"]}
    assert lines["Cat6 STP"] == 1


def test_bom_xlsx_upload_is_real_workbook() -> None:
    """The BOM xlsx upload opens back as a workbook (not stub bytes)."""
    # Arrange
    from io import BytesIO

    from openpyxl import load_workbook

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

    # Assert — round-trips as a real xlsx with a BOM sheet
    xlsx_url = next(
        u.url for u in urls if u.kind == ArtifactKind.BOM and u.format == "xlsx"
    )
    wb = load_workbook(BytesIO(client.uploads[xlsx_url]))
    assert wb.active is not None
    assert wb.active.title == "BOM"


def test_dtm_upload_is_real_dtm_json() -> None:
    """The DTM upload deserializes to a Dtm shape (not a stub)."""
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

    # Assert
    dtm_url = next(u.url for u in urls if u.kind == ArtifactKind.DTM)
    body = json.loads(client.uploads[dtm_url])
    assert body["deployment_uuid"] == str(DEPLOYMENT_ID)
    assert body["version"] == "1.0.0"
    assert "devices" in body


def test_sld_hmi_svg_upload_is_real_svg() -> None:
    """SLD_HMI_SVG upload is a parseable SVG with HMI's data-* hooks."""
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

    # Assert
    svg_url = next(u.url for u in urls if u.kind == ArtifactKind.SLD_HMI_SVG)
    body = client.uploads[svg_url].decode("utf-8")
    assert body.startswith("<?xml version=")
    assert 'data-comp="device-node"' in body or 'data-comp="bus"' in body

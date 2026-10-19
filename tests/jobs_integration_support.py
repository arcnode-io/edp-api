"""Payload and TestClient builders for the jobs integration tests; import explicitly."""

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from src.app_module import AppModule
from src.bom_generator.manifest_module import ManifestModule
from tests.manifest_fixture import commercial_ac_manifest_module


def _payload(deployment_id: UUID) -> dict[str, Any]:
    """Valid ConfiguratorPayload (v2, off-grid) as JSON dict."""
    return {
        "deployment_id": str(deployment_id),
        "operator_org": "acme",
        "deployment_site_name": "brookside dc-1",
        "contact_email": "ops@example.com",
        "primary_workload": "ai_training",
        "gpu_variant": "h100_sxm",
        "target_gpu_count": 56,
        "bess_coupling": "ac_coupled",
        "bess_capacity_mwh": 5.0,
        "climate_zone": "temperate",
        "deployment_context": "commercial",
        "aws_partition": "standard",
        "site": {
            "location": {"lat": 32.7, "lon": -96.8, "address": None},
            "country": "US",
            "state": "TX",
        },
        "onsite_generation": {"type": "none", "capacity_mw": None},
        "grid": {"path": "off_grid"},
    }


def _client() -> TestClient:
    """TestClient backed by AppModule with stub manifest (no S3 fetch)."""
    return TestClient(
        AppModule(manifest_module_override=commercial_ac_manifest_module()).create_app()
    )


def _client_with_uploads() -> tuple[TestClient, ManifestModule]:
    """TestClient + ManifestModule (stub captures uploads on .client.uploads)."""
    manifest_module = commercial_ac_manifest_module()
    app = AppModule(manifest_module_override=manifest_module).create_app()
    return TestClient(app), manifest_module

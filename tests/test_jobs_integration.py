"""Jobs HTTP integration tests against a real FastAPI TestClient."""

from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.app_module import AppModule
from src.bom_generator.manifest_module import ManifestModule, _StubManifestClient
from src.shared.schemas.artifact import ArtifactKind
from tests.manifest_fixture import commercial_ac_manifest_module


def _payload(deployment_id: UUID) -> dict[str, Any]:
    """Valid ConfiguratorPayload as JSON dict."""
    return {
        "deployment_id": str(deployment_id),
        "operator_org": "acme",
        "deployment_site_name": "brookside dc-1",
        "contact_email": "ops@example.com",
        "energy_source": "grid_hybrid",
        "source_capacity_mw": 10.0,
        "primary_workload": "ai_training",
        "gpu_variant": "h100_sxm",
        "target_gpu_count": 56,
        "bess_coupling": "ac_coupled",
        "bess_capacity_mwh": 5.0,
        "grid_connection": "grid_tied",
        "climate_zone": "temperate",
        "deployment_context": "commercial",
        "aws_partition": "standard",
        "wholesale_market": "ercot",
        "settlement_point": "HB_NORTH",
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


def test_post_then_get_roundtrip() -> None:
    """POST a job, then GET it by id, and confirm same artifact list."""
    # Arrange
    client = _client()
    deployment_id = uuid4()

    # Act — POST
    post = client.post("/edp-api/jobs", json=_payload(deployment_id))

    # Assert — 202 with URLs
    assert post.status_code == 202, post.text
    created = post.json()
    assert "job_id" in created
    assert created["status_url"].startswith("/edp-api/jobs/")
    assert len(created["edp_artifact_urls"]) > 0

    # Act — GET
    got = client.get(created["status_url"])

    # Assert — 200 + same urls. Status is "complete" because FastAPI's
    # BackgroundTask runs after the POST response ships and before the next
    # request; with the stub manifest the pipeline finishes synchronously.
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "complete", body
    assert body["edp_artifact_urls"] == created["edp_artifact_urls"]


def test_get_unknown_job_returns_404() -> None:
    """Unknown job_id returns 404."""
    # Arrange
    client = _client()
    unknown = uuid4()

    # Act
    response = client.get(f"/edp-api/jobs/{unknown}")

    # Assert
    assert response.status_code == 404


def test_sld_hmi_svg_is_produced_and_uploaded() -> None:
    """POST → BackgroundTask emits sld_hmi.svg to the deterministic S3 key."""
    # Arrange
    client, manifest_module = _client_with_uploads()
    deployment_id = uuid4()

    # Act — POST drives the pipeline through BackgroundTask before TestClient
    # returns control, so the upload is captured by the time we inspect.
    post = client.post("/edp-api/jobs", json=_payload(deployment_id))

    # Assert
    assert post.status_code == 202, post.text
    created = post.json()
    sld_hmi_url = next(
        u["url"]
        for u in created["edp_artifact_urls"]
        if u["kind"] == ArtifactKind.SLD_HMI_SVG.value
    )

    # The deterministic key follows s3://arcnode-artifacts/edp/{id}/sld_hmi.svg
    assert sld_hmi_url == f"s3://arcnode-artifacts/edp/{deployment_id}/sld_hmi.svg"

    # Pipeline upload landed in the stub client; bytes are a real SVG.
    stub = cast(_StubManifestClient, manifest_module.client)
    body = stub.uploads[sld_hmi_url].decode("utf-8")
    assert body.startswith("<?xml version=")
    assert "<svg" in body and "</svg>" in body


def test_re_render_endpoint_returns_fresh_svg_for_runtime_dtm() -> None:
    """POST /edp-api/sld-hmi-svg renders a Dtm body to SVG bytes.

    Lets ems-device-api re-render after runtime CRUD without re-running the
    full EDP pipeline; same authoring logic, no SVG-mutation duplication.
    """
    # Arrange — a tiny but valid Dtm body
    client = _client()
    dtm_body: dict[str, Any] = {
        "version": "1.0.0",
        "deployment_uuid": "00000000-0000-0000-0000-000000000aaa",
        "ems_mode": "sim",
        "sizing_params": {
            "P_compute_total_kW": 10.0,
            "E_BESS_total_kWh": 5000.0,
            "T_coolant_setpoint_C": 30.0,
        },
        "devices": {
            "bess_rack_1": {
                "device_id": "bess_rack_1",
                "template": "bess_rack",
                "connection": {"host": "10.0.0.1", "port": 502, "unit_id": "1"},
            }
        },
        "buses": [],
        "templates_used": {
            "bess_rack": {
                "template": "bess_rack",
                "kind": "leaf",
                "equipment_id": "EXT-BESS-001",
                "vendor": "Tesla",
                "model": "Megapack",
                "description": "test fixture",
                "measurements": {
                    "power": {
                        "unit": "watts",
                        "type": "float",
                        "binding": {
                            "protocol": "modbus_tcp",
                            "function_code": 4,
                            "address": 100,
                        },
                    }
                },
            }
        },
    }

    # Act
    response = client.post("/edp-api/sld-hmi-svg", json=dtm_body)

    # Assert
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/svg+xml"
    body = response.text
    assert body.startswith("<?xml version=")
    assert 'id="bess_rack_1"' in body


def test_post_rejects_invalid_payload() -> None:
    """Validator rejects defense_forward + dc_integrated_pcs (CATL exclusion)."""
    # Arrange
    client = _client()
    payload = _payload(uuid4())
    payload["deployment_context"] = "defense_forward"
    payload["bess_coupling"] = "dc_integrated_pcs"
    payload["aws_partition"] = "none"

    # Act
    response = client.post("/edp-api/jobs", json=payload)

    # Assert
    assert response.status_code == 422
    assert "CATL" in response.text

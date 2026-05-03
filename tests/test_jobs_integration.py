"""Jobs HTTP integration tests against a real FastAPI TestClient."""

from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.app_module import AppModule


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
    }


def _client() -> TestClient:
    return TestClient(AppModule().create_app())


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

    # Assert — 200 + same urls
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "running"
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

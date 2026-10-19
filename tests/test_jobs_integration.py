"""Jobs HTTP integration tests against a real FastAPI TestClient."""

from uuid import uuid4


from tests.jobs_integration_support import (
    _payload,
    _client,
)


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

    # Assert — 200 + same urls, now with counts. Status is "complete" because
    # FastAPI's BackgroundTask runs after the POST response ships and before
    # the next request; with the stub manifest the pipeline finishes
    # synchronously.
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "complete", body
    assert [u["url"] for u in body["edp_artifact_urls"]] == [
        u["url"] for u in created["edp_artifact_urls"]
    ]
    bom = next(u for u in body["edp_artifact_urls"] if u["kind"] == "bom")
    assert bom["summary"]["line_items"] > 0


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


def test_post_rejects_market_program_not_offered_in_region() -> None:
    """V4b (region-dependent, against the real config/grid_regions.yaml) -> 422.

    CAISO offers zero market_programs today — any grid_revenue payload
    targeting it is rejected by JobsService.create, not just by pydantic.
    """
    # Arrange
    client = _client()
    payload = _payload(uuid4())
    payload["grid"] = {
        "path": "grid_revenue",
        "service_type": "firm",
        "flex_obligation": None,
        "export_mode": "export",
        "market_access": "direct",
        "market_program": "ercot_ader",
        "settlement_point": "HB_NORTH",
        "wires_owner": {"id": "pge", "name": "PG&E", "type": "iou", "eia_id": None},
        "market_region": "caiso",
    }

    # Act
    response = client.post("/edp-api/jobs", json=payload)

    # Assert
    assert response.status_code == 422
    assert "not offered" in response.text

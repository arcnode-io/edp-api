"""Jobs produce the HMI SLD, and re-render it for a runtime DTM."""

from typing import Any, cast
from uuid import uuid4


from src.bom_generator.manifest_module import _StubManifestClient
from src.shared.schemas.artifact import ArtifactKind
from tests.jobs_integration_support import (
    _payload,
    _client,
    _client_with_uploads,
)


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
                            "data_type": "int16",
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

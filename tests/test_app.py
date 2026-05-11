from fastapi.testclient import TestClient
from src.app_module import AppModule

from tests.manifest_fixture import commercial_ac_manifest_module


def _app() -> AppModule:
    """AppModule with the manifest stubbed — no S3 hit at startup.

    Without the override, AppModule constructs a real ManifestModule that
    fetches manifest.yaml from S3. CI + dev machines without AWS creds
    would fail; the override keeps these tests environment-independent.
    """
    return AppModule(manifest_module_override=commercial_ac_manifest_module())


def test_healthcheck_endpoint() -> None:
    """Test the healthcheck endpoint returns 'ok'."""
    # Arrange
    app_module = _app()
    app = app_module.create_app()
    client = TestClient(app)
    expected_text = "ok"

    # Act
    response = client.get("/")

    # Assert
    assert response.text == expected_text


def test_app_startup_loads_template_catalog() -> None:
    """Catalog is loaded at app creation and stashed on app.state."""
    # Arrange / Act
    app_module = _app()
    app = app_module.create_app()

    # Assert
    assert hasattr(app.state, "template_catalog")
    catalog = app.state.template_catalog
    assert len(catalog) == 12  # 9 leaves + 3 modules
    assert "revenue_meter" in catalog
    assert "bess_module" in catalog

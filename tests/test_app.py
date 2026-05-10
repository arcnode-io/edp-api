from fastapi.testclient import TestClient
from src.app_module import AppModule


def test_healthcheck_endpoint() -> None:
    """Test the healthcheck endpoint returns 'ok'."""
    # Arrange
    app_module = AppModule()
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
    app_module = AppModule()
    app = app_module.create_app()

    # Assert
    assert hasattr(app.state, "template_catalog")
    catalog = app.state.template_catalog
    assert len(catalog) == 12  # 9 leaves + 3 modules
    assert "revenue_meter" in catalog
    assert "bess_module" in catalog

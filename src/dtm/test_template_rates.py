"""poll_rate_hz in the template catalog means a cadence the publisher keeps."""

from pathlib import Path

from src.dtm.template_loader import TemplateLoader
from src.shared.schemas.measurement import Publisher

_ROOT = Path(__file__).resolve().parents[2] / "device_templates"


def test_der_control_api_measurements_declare_no_rate() -> None:
    # Arrange — der-control-api publishes retained, on change only; a rate
    # would make consumers call a quiet channel stale
    catalog = TemplateLoader(root=_ROOT).load_catalog()

    # Act
    actual = {
        f"{name}.{m}": ms.poll_rate_hz
        for name, t in catalog.items()
        for m, ms in (t.measurements or {}).items()
        if ms.publisher == Publisher.DER_CONTROL_API and ms.poll_rate_hz is not None
    }

    # Assert
    assert actual == {}

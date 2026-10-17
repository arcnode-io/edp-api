"""Rated limits in the template catalog follow the hardware each template names."""

from pathlib import Path

import pytest

from src.dtm.template_loader import TemplateLoader

_ROOT = Path(__file__).resolve().parents[2] / "device_templates"


@pytest.mark.parametrize(
    ("template", "expected"),
    [("gpu_node", 1000.0), ("gpu_node_h100", 700.0)],
)
def test_gpu_power_tops_out_at_that_gpus_tdp(template: str, expected: float) -> None:
    # Arrange — B200 is 1000 W, H100 SXM 700 W; an H100 capped at 1000 W
    # would never alarm or bound a setpoint correctly
    catalog = TemplateLoader(root=_ROOT).load_catalog()
    measurements = catalog[template].measurements or {}

    # Act
    actual = {
        m.bounds.max
        for name, m in measurements.items()
        if name.startswith("gpu_") and "power" in name and m.bounds is not None
    }

    # Assert
    assert actual == {expected}

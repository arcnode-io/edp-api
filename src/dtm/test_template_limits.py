"""Rated limits in the template catalog follow the hardware each template names."""

import re
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
        if re.fullmatch(r"gpu_\d+_power(_limit)?", name) and m.bounds is not None
    }

    # Assert
    assert actual == {expected}


def test_h100_node_power_tops_out_at_its_psus_and_its_gpus_at_8x_tdp() -> None:
    # Arrange — 4x 5250 W PSUs run 2+2, so 10.5 kW usable; 8 GPUs x 700 W
    measurements = (
        TemplateLoader(root=_ROOT).load_catalog()["gpu_node_h100"].measurements
    )
    assert measurements is not None

    # Act
    actual = [
        b.max if (b := measurements[name].bounds) else None
        for name in ("power_consumed", "power_limit", "gpu_power_watts")
    ]

    # Assert
    assert actual == [10_500, 10_500, 5_600]


def test_battery_state_of_charge_spans_empty_to_full() -> None:
    # Arrange
    measurements = TemplateLoader(root=_ROOT).load_catalog()["bess_module"].measurements
    assert measurements is not None

    # Act
    bounds = measurements["state_of_charge"].bounds

    # Assert
    assert bounds is not None
    assert (bounds.min, bounds.max) == (0, 100)

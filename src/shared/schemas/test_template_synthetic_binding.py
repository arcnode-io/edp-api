"""Synthetic bindings: input modes, operations, and the gateway publisher."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    Measurement,
    Publisher,
    SyntheticBinding,
)


def test_synthetic_binding_happy_path() -> None:
    # Arrange / Act
    b = SyntheticBinding(
        protocol="synthetic",
        operation="subtract",
        inputs=[
            "sites/{site_id}/devices/operating_envelope/measurements/import_limit/watts",
            "sites/{site_id}/devices/{device_id}/measurements/active_power/watts",
        ],
    )
    # Assert
    assert b.operation == "subtract"
    assert b.inputs is not None
    assert len(b.inputs) == 2


def test_synthetic_binding_unbalance_over_three_phases() -> None:
    # Arrange
    phase_topics: list[str] = [
        f"sites/{{site_id}}/devices/{{device_id}}/measurements/phase_voltage_{p}/volts"
        for p in "abc"
    ]
    # Act
    b = SyntheticBinding(
        protocol="synthetic", operation="unbalance", inputs=phase_topics
    )
    # Assert
    assert (b.operation, b.inputs) == ("unbalance", phase_topics)


def test_synthetic_binding_source_measurement_mode() -> None:
    # Arrange / Act — projects one measurement across the device's children
    b = SyntheticBinding(
        protocol="synthetic",
        operation="weighted_mean",
        source_measurement="state_of_charge",
    )
    # Assert
    assert b.operation == "weighted_mean"
    assert b.source_measurement == "state_of_charge"
    assert b.inputs is None


def test_synthetic_binding_rejects_both_inputs_and_source_measurement() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        SyntheticBinding(
            protocol="synthetic",
            operation="sum",
            inputs=["a", "b"],
            source_measurement="active_power",
        )


def test_synthetic_binding_rejects_neither_inputs_nor_source_measurement() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        SyntheticBinding(protocol="synthetic", operation="sum")


def test_synthetic_binding_weighted_mean_requires_source_measurement_mode() -> None:
    # Arrange / Act / Assert — weighted_mean can't pair with a fixed inputs list
    with pytest.raises(ValidationError, match="weighted_mean requires"):
        SyntheticBinding(
            protocol="synthetic", operation="weighted_mean", inputs=["a", "b"]
        )


def test_synthetic_binding_subtract_requires_inputs_mode() -> None:
    # Arrange / Act / Assert — subtract can't pair with source_measurement
    with pytest.raises(ValidationError, match="subtract requires"):
        SyntheticBinding(
            protocol="synthetic",
            operation="subtract",
            source_measurement="active_power",
        )


def test_synthetic_binding_sum_valid_in_source_measurement_mode() -> None:
    # Arrange / Act — sum/mean/max/min work in either mode
    b = SyntheticBinding(
        protocol="synthetic", operation="sum", source_measurement="active_power"
    )
    # Assert
    assert b.operation == "sum"


def test_synthetic_measurement_requires_publisher_gateway() -> None:
    # Arrange / Act / Assert — synthetic binding without publisher = invalid
    with pytest.raises(
        ValidationError, match=r"binding\.protocol=synthetic requires publisher=gateway"
    ):
        Measurement(
            unit="watts",
            type="float",
            binding=SyntheticBinding(
                protocol="synthetic", operation="subtract", inputs=["a", "b"]
            ),
        )


def test_synthetic_measurement_rejects_non_gateway_publisher() -> None:
    # Arrange / Act / Assert — publisher must be GATEWAY when binding is synthetic
    with pytest.raises(
        ValidationError, match=r"binding\.protocol=synthetic requires publisher=gateway"
    ):
        Measurement(
            unit="watts",
            type="float",
            binding=SyntheticBinding(
                protocol="synthetic", operation="subtract", inputs=["a", "b"]
            ),
            publisher=Publisher.LOCAL_PROCESS,
        )


def test_synthetic_measurement_with_gateway_publisher_validates() -> None:
    # Arrange / Act
    m = Measurement(
        unit="watts",
        type="float",
        binding=SyntheticBinding(
            protocol="synthetic", operation="subtract", inputs=["a", "b"]
        ),
        publisher=Publisher.GATEWAY,
    )
    # Assert
    assert isinstance(m.binding, SyntheticBinding)
    assert m.publisher == Publisher.GATEWAY

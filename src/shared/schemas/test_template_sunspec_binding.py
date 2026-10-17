"""SunSpec bindings name a model and point; the gateway finds the address."""

from src.shared.schemas.template import Command, Measurement
from src.shared.schemas.template_protocols import SunspecBinding


def test_a_measurement_binds_to_a_sunspec_model_point() -> None:
    # Arrange — model 103 (inverter) W, wherever the device's model chain puts it
    raw = {
        "unit": "watts",
        "type": "float",
        "poll_rate_hz": 1,
        "binding": {"protocol": "sunspec", "model_id": 103, "point": "W"},
    }

    # Act
    actual = Measurement.model_validate(raw).binding

    # Assert
    assert actual == SunspecBinding(protocol="sunspec", model_id=103, point="W")


def test_a_command_can_drive_one_bit_of_a_bitfield_point() -> None:
    # Arrange — EPC model 65534 CmdBits bit 0 is the run enable
    raw = {
        "verb": "enable",
        "target": "run",
        "unit": "none",
        "payload": "bool",
        "binding": {
            "protocol": "sunspec",
            "model_id": 65534,
            "point": "CmdBits",
            "bit": 0,
        },
    }

    # Act
    actual = Command.model_validate(raw).binding

    # Assert
    assert isinstance(actual, SunspecBinding)
    assert (actual.point, actual.bit) == ("CmdBits", 0)

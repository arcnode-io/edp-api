"""TopologyYaml schema unit tests — new authoring shape per PR 2."""

import pytest
from pydantic import ValidationError

from src.dtm.topology_yaml import (
    TopologyBusMemberSpec,
    TopologyBusSpec,
    TopologyConnectionSpec,
    TopologyDeviceSpec,
    TopologyYaml,
)


def test_topology_device_spec_minimal() -> None:
    # Arrange / Act
    spec = TopologyDeviceSpec(
        template="poi_meter",
        description="ION9000",
        connection=TopologyConnectionSpec(
            host="mock-modbus-server", port=502, unit_id="2"
        ),
    )
    # Assert
    assert spec.template == "poi_meter"
    assert spec.connection is not None
    assert spec.connection.host == "mock-modbus-server"


def test_topology_device_spec_passive_has_no_connection() -> None:
    # Arrange / Act — passive equipment (e.g. switchgear) is drawn, not polled
    spec = TopologyDeviceSpec(template="switchgear", description="SafeGear")
    # Assert
    assert spec.connection is None


def test_topology_connection_accepts_sentinel_port() -> None:
    # Arrange / Act
    c = TopologyConnectionSpec(
        host="PROVISIONED_AT_COMMISSIONING",
        port="PROVISIONED_AT_COMMISSIONING",
        unit_id="PROVISIONED_AT_COMMISSIONING",
    )
    # Assert
    assert c.port == "PROVISIONED_AT_COMMISSIONING"


def test_topology_bus_spec_with_members() -> None:
    # Arrange / Act
    bus = TopologyBusSpec(
        bus_id="ac_main",
        type="ac",
        members=[
            TopologyBusMemberSpec(device_template="switchgear", port="line"),
            TopologyBusMemberSpec(device_template="poi_meter", port="voltage_in"),
        ],
    )
    # Assert
    assert bus.type == "ac"
    assert len(bus.members) == 2


def test_topology_yaml_full_shape() -> None:
    # Arrange / Act
    y = TopologyYaml(
        devices=[
            TopologyDeviceSpec(
                template="poi_meter",
                description="meter",
                connection=TopologyConnectionSpec(
                    host="mock-modbus-server", port=502, unit_id="2"
                ),
            ),
        ],
        buses=[
            TopologyBusSpec(
                bus_id="ac_main",
                type="ac",
                members=[
                    TopologyBusMemberSpec(
                        device_template="poi_meter", port="voltage_in"
                    )
                ],
            )
        ],
    )
    # Assert
    assert len(y.devices) == 1
    assert len(y.buses) == 1


def test_topology_bus_type_rejected_outside_dc_ac() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        TopologyBusSpec.model_validate(
            {"bus_id": "x", "type": "dontknow", "members": []}
        )


def test_topology_device_spec_rejects_unknown_field() -> None:
    # Arrange / Act / Assert — typo `tempate` should fail clearly
    with pytest.raises(ValidationError, match="extra"):
        TopologyDeviceSpec.model_validate(
            {
                "tempate": "poi_meter",  # typo
                "description": "x",
                "connection": {"host": "h", "port": 1},
            }
        )

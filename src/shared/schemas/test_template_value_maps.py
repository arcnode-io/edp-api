"""Bindings map a device's raw value or text to its label."""

from src.shared.schemas.template import (
    Dnp3Binding,
    ModbusBinding,
    RedfishBinding,
    SnmpBinding,
)


def test_binding_redfish_value_map_maps_device_text_to_label() -> None:
    # Arrange / Act — raw device text → our enum label
    b = RedfishBinding(
        protocol="redfish",
        uri="/ThermalEquipment/CDUs/1/Pumps/1",
        json_pointer="/Status/State",
        value_map={"Enabled": "ENABLED", "Disabled": "DISABLED"},
    )
    # Assert
    assert b.value_map == {"Enabled": "ENABLED", "Disabled": "DISABLED"}
    assert RedfishBinding(protocol="redfish", uri="/Chassis/1").value_map is None


def test_register_and_point_bindings_map_raw_value_to_label() -> None:
    # Arrange / Act — raw integer, as a string, → our enum label
    modbus = ModbusBinding(
        protocol="modbus_tcp",
        function_code=3,
        address=53249,
        data_type="uint16",
        value_map={"0": "AUTOMATIC_INTERNAL"},
    )
    dnp3 = Dnp3Binding(
        protocol="dnp3_tcp",
        point_index=1,
        point_type="analog_input",
        value_map={"1": "STALE"},
    )
    snmp = SnmpBinding(
        protocol="snmp", oid="1.3.6.1.2.1.2.2.1.8.1", value_map={"1": "UP"}
    )
    # Assert
    assert modbus.value_map == {"0": "AUTOMATIC_INTERNAL"}
    assert dnp3.value_map == {"1": "STALE"}
    assert snmp.value_map == {"1": "UP"}

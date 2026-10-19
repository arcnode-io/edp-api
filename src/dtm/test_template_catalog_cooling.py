"""Real catalog: CDU and dry cooler templates, and enum label maps."""

from pathlib import Path


from src.dtm.template_loader import TemplateLoader
from src.shared.schemas.template import (
    ModbusBinding,
    RedfishBinding,
    SyntheticBinding,
)


def test_load_real_catalog_cdu_reads_dmtf_cooling_unit() -> None:
    # Arrange — DMTF CoolingUnit / CoolantConnector / Pump; MCDU-10 lists Redfish
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    cdu = catalog["cdu"].measurements
    connector = "/ThermalEquipment/CDUs/1/SecondaryCoolantConnectors/1"
    pump = "/ThermalEquipment/CDUs/1/Pumps/1"

    def redfish(name: str) -> tuple[str, str | None]:
        binding = cdu[name].binding
        assert isinstance(binding, RedfishBinding)
        return (binding.uri, binding.json_pointer)

    # Act / Assert
    assert redfish("supply_temp") == (connector, "/SupplyTemperatureCelsius/Reading")
    assert redfish("return_temp") == (connector, "/ReturnTemperatureCelsius/Reading")
    assert redfish("pump_flow_rate") == (connector, "/FlowLitersPerMinute/Reading")
    assert redfish("pump_speed") == (pump, "/PumpSpeedPercent/Reading")
    assert redfish("pump_state") == (pump, "/Status/State")
    state = cdu["pump_state"].binding
    assert isinstance(state, RedfishBinding) and state.value_map is not None
    assert len(state.value_map) == 13  # every DMTF Resource.State value
    assert state.value_map["Enabled"] == "ENABLED"


def test_every_polled_enum_maps_raw_values_to_its_labels() -> None:
    # Arrange — the gateway publishes value_map[raw]; JSON Schema enum = `values`
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    polled_enums = [
        (t.template, name, m)
        for t in catalog.values()
        for name, m in t.measurements.items()
        if m.type == "enum"
        and m.binding is not None
        and not isinstance(m.binding, SyntheticBinding)
    ]
    # Act / Assert
    assert polled_enums
    for template, name, m in polled_enums:
        value_map = getattr(m.binding, "value_map", None)
        assert value_map, f"{template}.{name} has no value_map"
        assert m.values is not None
        assert set(value_map.values()) == set(m.values.values()), f"{template}.{name}"


def test_load_real_catalog_dc_external_matches_guentner_gmm_spec() -> None:
    # Arrange — Güntner "Modbus GMM" interface spec V3.0
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    dc = catalog["dc_external"]

    def modbus(name: str) -> ModbusBinding:
        binding = dc.measurements[name].binding
        assert isinstance(binding, ModbusBinding)
        return binding

    # Act / Assert
    assert (
        modbus("leaving_fluid_temp").function_code,
        modbus("leaving_fluid_temp").address,
    ) == (4, 53508)
    assert modbus("entering_fluid_temp").address == 53511
    assert modbus("ambient_temp").address == 53513
    assert (modbus("fan_1_speed").address, modbus("fan_2_speed").address) == (
        53633,
        53634,
    )
    assert (
        modbus("operating_mode").function_code,
        modbus("operating_mode").address,
    ) == (3, 53249)
    assert dc.measurements["operating_mode"].values == {
        0: "AUTOMATIC_INTERNAL",
        1: "AUTOMATIC_EXTERNAL_ANALOG",
        2: "AUTOMATIC_EXTERNAL_BUS",
        3: "SLAVE_EXTERNAL_ANALOG",
        4: "SLAVE_EXTERNAL_BUS",
    }
    assert modbus("fault_word").address == 53616
    assert "unit_state" not in dc.measurements
    setpoint = dc.commands["set_leaving_fluid_temp"].binding
    assert isinstance(setpoint, ModbusBinding)
    assert (setpoint.function_code, setpoint.address, setpoint.scale) == (6, 53257, 0.1)

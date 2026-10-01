"""TemplateLoader unit tests using tmp_path fixtures."""

from pathlib import Path

import pytest

from src.dtm.template_loader import TemplateLoader, TemplateLoadError
from src.shared.schemas.template import (
    DistributeBinding,
    Dnp3Binding,
    ModbusBinding,
    RedfishBinding,
    SnmpBinding,
    SyntheticBinding,
)


def test_load_catalog_empty_dir(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    loader = TemplateLoader(root=tmp_path)
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert catalog == {}


def _write_poi_meter(dir_: Path) -> None:
    (dir_ / "poi_meter.yaml").write_text("""
template: poi_meter
kind: leaf
equipment_id: GRD-MTR-001
vendor: Schneider Electric
model: ION9000
description: test
measurements:
  voltage_a:
    unit: volts
    type: float
    binding:
      protocol: modbus_tcp
      function_code: 4
      address: 100
      data_type: int16
""".lstrip())


def test_load_catalog_loads_one_leaf(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_poi_meter(tmp_path / "leaf")
    loader = TemplateLoader(root=tmp_path)
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "poi_meter" in catalog
    assert catalog["poi_meter"].equipment_id == "GRD-MTR-001"


def test_load_catalog_raises_on_invalid_yaml(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    (tmp_path / "leaf" / "broken.yaml").write_text("template: : :\n")
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="invalid YAML"):
        loader.load_catalog()


def test_load_catalog_raises_on_validation_failure(tmp_path: Path) -> None:
    # Arrange — leaf missing its required vendor
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    (tmp_path / "leaf" / "bad.yaml").write_text("""
template: no_vendor
kind: leaf
equipment_id: GRD-MTR-001
model: T-1
description: missing vendor
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="schema validation failed"):
        loader.load_catalog()


def test_load_real_catalog_includes_poi_meter() -> None:
    # Arrange — real device_templates/ at repo root
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "poi_meter" in catalog
    rm = catalog["poi_meter"]
    assert rm.equipment_id == "GRD-MTR-001"
    # ION9000 Modbus map 004.005.000; the meter answers FC3 only as a slave
    expected = {
        "active_power": (3060, "float32"),  # + = imported/delivered
        "kwh_delivered": (3204, "int64"),
        "kwh_received": (3208, "int64"),
        "power_factor": (3150, "float32"),
        "thd_voltage_a": (21330, "float32"),
        "thd_voltage_b": (21332, "float32"),
        "thd_voltage_c": (21334, "float32"),
    }
    actual = {}
    for name in expected:
        binding = rm.measurements[name].binding
        assert isinstance(binding, ModbusBinding)
        assert binding.function_code == 3
        assert binding.scale == 1.0
        actual[name] = (binding.address, binding.data_type)
    assert actual == expected


def test_load_real_catalog_pdu_matches_sentry4_mib() -> None:
    # Arrange — Sentry4-MIB; index = unit(1).cord(1).line|phase
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    pdu = catalog["pdu"].measurements
    line_current = "1.3.6.1.4.1.1718.4.1.4.3.1.3.1.1."  # st4LineCurrent
    phase_voltage = "1.3.6.1.4.1.1718.4.1.5.3.1.3.1.1."  # st4PhaseVoltage

    def snmp(name: str) -> tuple[str, float]:
        binding = pdu[name].binding
        assert isinstance(binding, SnmpBinding)
        return (binding.oid, binding.scale)

    # Act / Assert
    for n in (1, 2, 3):
        assert snmp(f"input_current_l{n}") == (f"{line_current}{n}", 0.01)
        assert snmp(f"input_voltage_l{n}") == (f"{phase_voltage}{n}", 0.1)
    assert set(pdu) == {
        f"input_{q}_l{n}" for q in ("current", "voltage") for n in (1, 2, 3)
    }


def test_load_real_catalog_network_switch_reads_standard_mibs() -> None:
    # Arrange — SN5600 runs Cumulus Linux: IF-MIB + ENTITY-SENSOR-MIB, no Redfish
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    switch = catalog["network_switch"].measurements
    # Act / Assert
    for binding in (m.binding for m in switch.values()):
        assert isinstance(binding, SnmpBinding)
    port = switch["port_link_status"]
    assert isinstance(port.binding, SnmpBinding)
    assert port.binding.oid.startswith("1.3.6.1.2.1.2.2.1.8.")  # ifOperStatus
    assert port.values == {
        1: "UP",
        2: "DOWN",
        3: "TESTING",
        4: "UNKNOWN",
        5: "DORMANT",
        6: "NOT_PRESENT",
        7: "LOWER_LAYER_DOWN",
    }
    for temp in ("inlet_temp", "asic_temp"):
        binding = switch[temp].binding
        assert isinstance(binding, SnmpBinding)
        assert binding.oid.startswith("1.3.6.1.2.1.99.1.1.1.4.")  # entPhySensorValue
    assert set(switch) == {"port_link_status", "inlet_temp", "asic_temp"}


def test_load_real_catalog_gpu_node_reads_nvidia_hgx_per_gpu() -> None:
    # Arrange — NVIDIA DGX B200 Redfish docs + NVIDIA/bmcweb nvidia_processor.hpp
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    gpu = catalog["gpu_node"].measurements
    base = "/Systems/HGX_Baseboard_0/Processors/GPU_SXM_"

    def redfish(name: str) -> RedfishBinding:
        binding = gpu[name].binding
        assert isinstance(binding, RedfishBinding)
        return binding

    # Act / Assert
    for n in range(1, 9):
        power = redfish(f"gpu_{n}_power")
        assert (power.uri, power.json_pointer) == (
            f"{base}{n}/EnvironmentMetrics",
            "/PowerWatts/Reading",
        )
        limit = redfish(f"gpu_{n}_power_limit")
        assert limit.json_pointer == "/PowerLimitWatts/SetPoint"
        clock = redfish(f"gpu_{n}_clock")
        assert (clock.uri, clock.json_pointer, clock.scale) == (
            f"{base}{n}/ProcessorMetrics",
            "/OperatingSpeedMHz",
            1e6,
        )
        throttle = redfish(f"gpu_{n}_throttle_reason")
        assert throttle.json_pointer == "/Oem/Nvidia/ThrottleReasons/0"
        assert throttle.value_map is not None
        assert throttle.value_map["SWPowerCap"] == 1
        assert gpu[f"gpu_{n}_throttle_reason"].values is not None
    total = gpu["gpu_power_watts"].binding
    assert isinstance(total, SyntheticBinding)
    assert total.operation == "sum"
    assert total.inputs is not None and len(total.inputs) == 8


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
    assert state.value_map["Enabled"] == 0


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


def test_load_real_catalog_includes_bess_rack_capacity_kwh() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert — Tesla Megapack 2 XL's own description says "4 MWh"
    assert catalog["bess_rack"].capacity_kwh == 4000.0


def test_load_real_catalog_includes_bess_module() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "bess_module" in catalog
    m = catalog["bess_module"]
    assert m.kind.value == "module"
    assert m.equipment_id is None
    assert m.contains[0].template == "bess_rack"

    # Rollup measurements are real synthetic bindings now, not bare local_process
    active_power = m.measurements["active_power"]
    assert active_power.publisher is not None
    assert active_power.publisher.value == "gateway"
    ap_binding = active_power.binding
    assert isinstance(ap_binding, SyntheticBinding)
    assert ap_binding.operation == "sum"
    assert ap_binding.source_measurement == "active_power"

    reactive_power = m.measurements["reactive_power"]
    rp_binding = reactive_power.binding
    assert isinstance(rp_binding, SyntheticBinding)
    assert rp_binding.operation == "sum"
    assert rp_binding.source_measurement == "reactive_power"

    soc = m.measurements["state_of_charge"]
    soc_binding = soc.binding
    assert isinstance(soc_binding, SyntheticBinding)
    assert soc_binding.operation == "weighted_mean"
    assert soc_binding.source_measurement == "state_of_charge"

    # Headroom is referenced to POI net power (+ = import): import headroom
    # is import_limit - P_poi, export headroom is export_limit + P_poi.
    poi_power = (
        "sites/{site_id}/devices/{poi_meter_device_id}/measurements/active_power/watts"
    )
    import_headroom = m.measurements["import_headroom"].binding
    assert isinstance(import_headroom, SyntheticBinding)
    assert import_headroom.operation == "subtract"
    assert import_headroom.inputs == [
        "sites/{site_id}/devices/operating_envelope/measurements/import_limit/watts",
        poi_power,
    ]
    export_headroom = m.measurements["export_headroom"].binding
    assert isinstance(export_headroom, SyntheticBinding)
    assert export_headroom.operation == "sum"
    assert export_headroom.inputs == [
        "sites/{site_id}/devices/operating_envelope/measurements/export_limit/watts",
        poi_power,
    ]

    # set_active_power fans out via the real distribute binding + control law
    set_active_power = m.commands["set_active_power"]
    dist_binding = set_active_power.binding
    assert isinstance(dist_binding, DistributeBinding)
    assert dist_binding.allocation_policy == "soc_weighted"
    assert dist_binding.ramp_rate_per_sec == 0.10
    assert dist_binding.hysteresis_margin == 0.05
    assert dist_binding.hysteresis_dwell_secs == 30.0

    # set_reactive_power untouched — still the generic local-process fanout
    set_reactive_power = m.commands["set_reactive_power"]
    assert set_reactive_power.fanout is not None
    assert set_reactive_power.fanout.value == "local_process"


def test_load_real_catalog_size() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    leaves = [t for t in catalog.values() if t.kind.value == "leaf"]
    modules = [t for t in catalog.values() if t.kind.value == "module"]
    assert len(leaves) == 13
    assert len(modules) == 3


def test_load_real_catalog_includes_der_dispatch() -> None:
    """Recreated to match ems-der-control-api's post-clean-slate rebuild
    (DispatchPublisher/DispatchState/DispatchCommandSubscriber) — not the
    old shape resurrected blindly, verified against that repo's real code.
    """
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    dd = catalog["der_dispatch"]
    assert dd.kind.value == "leaf"

    tap = dd.measurements["target_active_power"]
    assert tap.publisher is not None and tap.publisher.value == "der_control_api"
    assert tap.binding is None

    der_event_state = dd.measurements["der_event_state"]
    assert der_event_state.type == "enum"
    assert der_event_state.values == {
        0: "IDLE",
        1: "PENDING",
        2: "ARMED",
        3: "ACTIVE",
        4: "REJECTED",
    }

    shortfall = dd.measurements["dispatch_shortfall"]
    assert shortfall.type == "bool"
    assert shortfall.publisher is not None
    assert shortfall.publisher.value == "der_control_api"

    # Gateway-computed, no binding: it sums whatever distribute-parent
    # devices exist (ems-industrial-gateway/src/der_dispatch.rs), a formula
    # that doesn't fit either existing synthetic mode (der_dispatch has no
    # contains: relationship to bess_module — siblings, not parent/child).
    # local_process, not gateway: Publisher.GATEWAY's own docstring promises
    # it's always paired with a synthetic binding, which doesn't apply here.
    actual = dd.measurements["actual_active_power"]
    assert actual.type == "float"
    assert actual.publisher is not None
    assert actual.publisher.value == "local_process"
    assert actual.binding is None

    approve = dd.commands["approve_dispatch"]
    assert approve.verb == "enable"
    assert approve.target == "event_active"
    assert approve.fanout is not None and approve.fanout.value == "der_control_api"

    reject = dd.commands["reject_dispatch"]
    assert reject.verb == "disable"
    assert reject.target == "event_active"
    assert reject.fanout is not None and reject.fanout.value == "der_control_api"


def test_load_real_catalog_includes_switchgear_voltage_unbalance() -> None:
    """Grid HMI screen — local_process-computed, no direct binding (needs all 3 phases)."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    unbalance = catalog["switchgear"].measurements["voltage_unbalance_pct"]
    assert (
        unbalance.publisher is not None and unbalance.publisher.value == "local_process"
    )
    assert unbalance.binding is None


def test_load_real_catalog_protective_relay_matches_sel_351_dnp_profile() -> None:
    """SEL-351-5/-6/-7 DNP3 device profile default map (dnpDP-351R100)."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    relay = catalog["protective_relay"].measurements

    def point(name: str) -> tuple[str, int, float]:
        binding = relay[name].binding
        assert isinstance(binding, Dnp3Binding)
        return (binding.point_type, binding.point_index, binding.scale)

    # Act / Assert — magnitudes only; odd AI indices are angles
    assert point("phase_a_current") == ("analog_input", 0, 1.0)
    assert point("phase_b_current") == ("analog_input", 2, 1.0)
    assert point("phase_c_current") == ("analog_input", 4, 1.0)
    assert point("phase_voltage_a") == ("analog_input", 8, 1000.0)  # kV primary
    assert point("phase_voltage_b") == ("analog_input", 10, 1000.0)
    assert point("phase_voltage_c") == ("analog_input", 12, 1000.0)
    assert point("trip_status") == ("binary_input", 9, 1.0)
    assert point("ground_fault") == ("binary_input", 15, 1.0)
    # User-settable slots, configured into the relay's DNP map at commissioning
    assert point("anti_islanding_armed") == ("binary_input", 24, 1.0)
    assert point("ride_through_enabled") == ("binary_input", 25, 1.0)
    assert "reconnect_delay_s" not in relay
    assert not any(n.startswith("line_voltage_") for n in relay)


def test_load_real_catalog_includes_pv_inverter() -> None:
    """Grid HMI screen — PV output per inverter, scalable member of grid_module."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    pv = catalog["pv_inverter"]
    assert pv.kind.value == "leaf"
    assert pv.measurements["active_power"].type == "float"
    # SunSpec model 103 after Common at base 40000: W at 40084, W_SF at 40085
    binding = pv.measurements["active_power"].binding
    assert isinstance(binding, ModbusBinding)
    assert (binding.function_code, binding.address, binding.data_type) == (
        3,
        40084,
        "int16",
    )
    assert binding.scale_factor_address == 40085
    grid_module = catalog["grid_module"]
    assert any(
        c.template == "pv_inverter" and c.qty == "scalable"
        for c in grid_module.contains
    )


def test_load_real_catalog_includes_compute_and_grid_modules() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "compute_module" in catalog
    assert "grid_module" in catalog
    cm = catalog["compute_module"]
    gm = catalog["grid_module"]
    assert cm.kind.value == "module"
    assert gm.kind.value == "module"
    assert any(c.template == "gpu_node" for c in cm.contains)
    assert any(c.template == "switchgear" for c in gm.contains)


def test_load_catalog_rejects_duplicate_slug(tmp_path: Path) -> None:
    # Arrange — two files claiming the same slug
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_poi_meter(tmp_path / "leaf")
    (tmp_path / "leaf" / "poi_meter_dup.yaml").write_text("""
template: poi_meter
kind: leaf
equipment_id: GRD-MTR-001
vendor: Schneider Electric
model: ION9000
description: dup
measurements:
  v:
    unit: volts
    type: float
    binding: { protocol: modbus_tcp, function_code: 4, address: 100, data_type: int16 }
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="duplicate template slug"):
        loader.load_catalog()


def test_load_catalog_rejects_unresolved_contains(tmp_path: Path) -> None:
    # Arrange — module references a leaf that doesn't exist
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_poi_meter(tmp_path / "leaf")
    (tmp_path / "module" / "broken_module.yaml").write_text("""
template: broken_module
kind: module
description: refs a leaf that doesn't exist
contains:
  - template: nonexistent_leaf
    qty: 1
measurements:
  rollup:
    unit: watts
    type: float
    publisher: local_process
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="not in catalog"):
        loader.load_catalog()

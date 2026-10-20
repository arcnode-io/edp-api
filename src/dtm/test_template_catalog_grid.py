"""Real catalog: grid-side templates (POI meter, switchgear, relay, PV)."""

from pathlib import Path


from src.dtm.template_loader import TemplateLoader
from src.shared.schemas.template import (
    Dnp3Binding,
    ModbusBinding,
    SyntheticBinding,
)


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
        "frequency": (3110, "float32"),
    }
    actual = {}
    for name in expected:
        binding = rm.measurements[name].binding
        assert isinstance(binding, ModbusBinding)
        assert binding.function_code == 3
        assert binding.scale == 1.0
        actual[name] = (binding.address, binding.data_type)
    assert actual == expected


def test_load_real_catalog_switchgear_is_passive_relay_carries_its_readings() -> None:
    """SafeGear has no comms; the SEL relay in it reports breaker and bus values."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    # Act
    switchgear = catalog["switchgear"]
    relay = catalog["protective_relay"].measurements
    # Assert
    assert switchgear.measurements == {} and switchgear.commands == {}
    breaker = relay["breaker_closed"].binding
    assert isinstance(breaker, Dnp3Binding)
    assert (breaker.point_type, breaker.point_index) == ("binary_input", 0)  # 52A
    unbalance = relay["voltage_unbalance_pct"].binding
    assert isinstance(unbalance, SyntheticBinding)
    assert unbalance.operation == "unbalance"
    assert unbalance.inputs == [
        f"sites/{{site_id}}/devices/{{device_id}}/measurements/phase_voltage_{p}/volts"
        for p in "abc"
    ]


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


def test_grid_module_rollups_come_from_the_poi_meter() -> None:
    """Net power and frequency are synthetics over the one POI meter."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    # Act
    measurements = catalog["grid_module"].measurements
    actual = {
        name: (b.operation, b.source_measurement, b.child_template)
        for name in ("net_active_power", "grid_frequency")
        if isinstance(b := measurements[name].binding, SyntheticBinding)
    }
    # Assert
    assert actual == {
        "net_active_power": ("sum", "active_power", "poi_meter"),
        "grid_frequency": ("mean", "frequency", "poi_meter"),
    }

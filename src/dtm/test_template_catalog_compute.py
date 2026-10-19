"""Real catalog: compute container IT templates read what their devices publish."""

from pathlib import Path


from src.dtm.template_loader import TemplateLoader
from src.shared.schemas.template_module_bindings import PowerCapBinding
from src.shared.schemas.template import (
    RedfishBinding,
    SnmpBinding,
    SyntheticBinding,
)


def test_load_real_catalog_pdu_matches_pdu2_mib() -> None:
    # Arrange — Raritan PDU2-MIB (all Xerus PDUs); pduId 1, inletId 1
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    pdu = catalog["pdu"].measurements
    pole = "1.3.6.1.4.1.13742.6.5.2.4.1.4.1.1."  # measurementsInletPoleSensorValue

    def snmp(name: str) -> tuple[str, float]:
        binding = pdu[name].binding
        assert isinstance(binding, SnmpBinding)
        return (binding.oid, binding.scale)

    # Act / Assert — sensor types: rmsCurrent 1, rmsVoltage 4, activePower 5
    for n in (1, 2, 3):
        assert snmp(f"input_current_l{n}") == (f"{pole}{n}.1", 0.001)
        assert snmp(f"input_voltage_l{n}") == (f"{pole}{n}.4", 1.0)
    assert snmp("input_power") == ("1.3.6.1.4.1.13742.6.5.2.3.1.4.1.1.5", 1.0)


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
        assert throttle.value_map["SWPowerCap"] == "SW_POWER_CAP"
        assert gpu[f"gpu_{n}_throttle_reason"].values is not None
    total = gpu["gpu_power_watts"].binding
    assert isinstance(total, SyntheticBinding)
    assert total.operation == "sum"
    assert total.inputs is not None and len(total.inputs) == 8


def test_load_real_catalog_gpu_node_caps_each_gpu_where_it_reads_the_limit() -> None:
    """DGX B200 guide: PATCH EnvironmentMetrics PowerLimitWatts.SetPoint per GPU."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    node = TemplateLoader(root=repo_root / "device_templates").load_catalog()[
        "gpu_node"
    ]
    # Act / Assert
    for n in range(1, 9):
        command = node.commands[f"set_gpu_{n}_power_limit"]
        assert (command.verb, command.target, command.unit) == (
            "set",
            f"gpu_{n}_power_limit",
            "watts",
        )
        limit = node.measurements[f"gpu_{n}_power_limit"]
        assert command.binding == limit.binding
        assert limit.bounds is not None
        assert (limit.bounds.min, limit.bounds.max, limit.bounds.nominal) == (
            200,
            1000,
            1000,
        )


def test_load_real_catalog_compute_module_rolls_up_pdus_and_caps_gpus() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    module = catalog["compute_module"]
    # Act
    total = module.measurements["total_power"].binding
    cap = module.commands["set_power_limit"]
    # Assert — PDUs feed everything in the container, so they're the total
    assert isinstance(total, SyntheticBinding)
    assert (total.operation, total.source_measurement, total.child_template) == (
        "sum",
        "input_power",
        "pdu",
    )
    assert "input_power" in catalog["pdu"].measurements
    assert isinstance(cap.binding, PowerCapBinding)
    assert (cap.verb, cap.target, cap.unit) == ("set", "power_limit", "percent")
    assert cap.binding.child_template == "gpu_node"
    assert set(cap.binding.child_commands) == set(catalog["gpu_node"].commands)

"""TemplateLoader unit tests using tmp_path fixtures."""

from pathlib import Path

import pytest

from src.dtm.template_loader import TemplateLoader, TemplateLoadError
from src.shared.schemas.template import DistributeBinding, SyntheticBinding


def test_load_catalog_empty_dir(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    loader = TemplateLoader(root=tmp_path)
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert catalog == {}


def _write_revenue_meter(dir_: Path) -> None:
    (dir_ / "revenue_meter.yaml").write_text("""
template: revenue_meter
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
""".lstrip())


def test_load_catalog_loads_one_leaf(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_revenue_meter(tmp_path / "leaf")
    loader = TemplateLoader(root=tmp_path)
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "revenue_meter" in catalog
    assert catalog["revenue_meter"].equipment_id == "GRD-MTR-001"


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
    # Arrange — leaf with no measurements/commands
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    (tmp_path / "leaf" / "bad.yaml").write_text("""
template: empty
kind: leaf
equipment_id: GRD-MTR-001
vendor: Test
model: T-1
description: empty
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="schema validation failed"):
        loader.load_catalog()


def test_load_real_catalog_includes_revenue_meter() -> None:
    # Arrange — real device_templates/ at repo root
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "revenue_meter" in catalog
    rm = catalog["revenue_meter"]
    assert rm.equipment_id == "GRD-MTR-001"
    assert "kwh_delivered" in rm.measurements


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

    dispatch_state = dd.measurements["dispatch_state"]
    assert dispatch_state.type == "enum"
    assert dispatch_state.values == {
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


def test_load_real_catalog_includes_protective_relay_islanding_fields() -> None:
    """Grid HMI screen — anti-islanding/ride-through belong to the protection relay."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    relay = catalog["protective_relay"].measurements
    assert relay["anti_islanding_armed"].type == "bool"
    assert relay["ride_through_enabled"].type == "bool"
    assert relay["reconnect_delay_s"].type == "float"


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
    _write_revenue_meter(tmp_path / "leaf")
    (tmp_path / "leaf" / "revenue_meter_dup.yaml").write_text("""
template: revenue_meter
kind: leaf
equipment_id: GRD-MTR-001
vendor: Schneider Electric
model: ION9000
description: dup
measurements:
  v:
    unit: volts
    type: float
    binding: { protocol: modbus_tcp, function_code: 4, address: 100 }
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="duplicate template slug"):
        loader.load_catalog()


def test_load_catalog_rejects_unresolved_contains(tmp_path: Path) -> None:
    # Arrange — module references a leaf that doesn't exist
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_revenue_meter(tmp_path / "leaf")
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

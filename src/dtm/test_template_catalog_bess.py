"""Real catalog: battery rack and module templates."""

from pathlib import Path


from src.dtm.template_loader import TemplateLoader
from src.shared.schemas.template import (
    DistributeBinding,
    ModbusBinding,
    SyntheticBinding,
)


def test_load_real_catalog_includes_bess_rack_capacity_kwh() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert — EXT-BESS-001: Megapack 2 XL 2-hour, 1927 kW / 3854 kWh
    assert catalog["bess_rack"].capacity_kwh == 3854.0
    # sizing can hold the pack near full (readiness), so no high-SoC warning
    soc = catalog["bess_rack"].measurements["state_of_charge"].thresholds
    assert soc is not None and (soc.warn_max, soc.alarm_max) == (100, 100)


def test_load_real_catalog_bess_rack_reports_its_present_power_limits() -> None:
    # Arrange — the BMS/PCS derate with SoC, so read the limits, don't assume rated
    repo_root = Path(__file__).resolve().parents[2]
    rack = TemplateLoader(root=repo_root / "device_templates").load_catalog()[
        "bess_rack"
    ]
    # Act
    limits = [rack.measurements[n] for n in ("max_charge_power", "max_discharge_power")]
    # Assert — positive magnitudes in watts up to the 1927 kW rating, polled
    for limit in limits:
        assert limit.unit == "watts" and limit.bounds is not None
        assert (limit.bounds.min, limit.bounds.max) == (0, 1927000)
        assert isinstance(limit.binding, ModbusBinding)
    active = rack.measurements["active_power"].bounds
    assert active is not None and (active.min, active.max) == (-1927000, 1927000)


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

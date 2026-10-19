"""Unit tests for TemplateKind/Publisher/Fanout enums and DeviceTemplate validators."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    ContainsEntry,
    DeviceTemplate,
    Fanout,
    Measurement,
    Publisher,
    TemplateKind,
)
from src.shared.schemas.template_test_support import (
    _mb,
    _mv,
)

# --- Enum sanity ---


def test_enum_values() -> None:
    assert TemplateKind.LEAF == "leaf"
    assert TemplateKind.MODULE == "module"
    assert Publisher.LOCAL_PROCESS == "local_process"
    assert Publisher.ANALYST == "analyst"
    assert Publisher.DER_CONTROL_API == "der_control_api"
    assert Fanout.LOCAL_PROCESS == "local_process"
    assert Fanout.DER_CONTROL_API == "der_control_api"


# --- DeviceTemplate happy paths ---


def test_device_template_leaf_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="poi_meter",
        kind=TemplateKind.LEAF,
        equipment_id="GRD-MTR-001",
        vendor="Schneider Electric",
        model="ION9000",
        description="test",
        measurements={
            "voltage_a": Measurement(unit="volts", type="float", binding=_mb())
        },
    )
    # Assert
    assert t.kind == TemplateKind.LEAF
    assert t.equipment_id == "GRD-MTR-001"


def test_device_template_capacity_kwh_defaults_none() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="poi_meter",
        kind=TemplateKind.LEAF,
        equipment_id="GRD-MTR-001",
        vendor="Schneider Electric",
        model="ION9000",
        description="test",
        measurements={
            "voltage_a": Measurement(unit="volts", type="float", binding=_mb())
        },
    )
    # Assert
    assert t.capacity_kwh is None


def test_device_template_capacity_kwh_accepts_nameplate_value() -> None:
    # Arrange / Act — bess_rack's 4 MWh nameplate, as capacity_kwh
    t = DeviceTemplate(
        template="bess_rack",
        kind=TemplateKind.LEAF,
        equipment_id="EXT-BESS-001",
        vendor="Tesla",
        model="Megapack 2 XL",
        description="test",
        capacity_kwh=4000.0,
        measurements={"soc": Measurement(unit="percent", type="float", binding=_mb())},
    )
    # Assert
    assert t.capacity_kwh == 4000.0


def test_device_template_module_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="bess_module",
        kind=TemplateKind.MODULE,
        description="BESS module aggregation",
        contains=[ContainsEntry(template="bess_rack", qty="scalable")],
        measurements={
            "state_of_charge": Measurement(
                unit="percent", type="float", publisher=Publisher.LOCAL_PROCESS
            )
        },
    )
    # Assert
    assert t.kind == TemplateKind.MODULE
    assert t.equipment_id is None
    assert t.contains[0].template == "bess_rack"


# --- Slug validator ---


def test_template_slug_format_rejected() -> None:
    with pytest.raises(ValidationError, match="slug"):
        DeviceTemplate(
            template="Poi-Meter",  # uppercase + dash → invalid
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            description="test",
            measurements=_mv(),
        )

"""Unit tests for TemplateKind/Publisher/Fanout enums and DeviceTemplate validators."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    ContainsEntry,
    DeviceTemplate,
    Fanout,
    Measurement,
    ModbusBinding,
    Publisher,
    TemplateKind,
)


def _mb() -> ModbusBinding:
    return ModbusBinding(protocol="modbus_tcp", function_code=4, address=100)


def _mv() -> dict[str, Measurement]:
    """Single float voltage measurement — reused across validator tests."""
    return {"v": Measurement(unit="volts", type="float", binding=_mb())}


def _ms() -> dict[str, Measurement]:
    """Single publisher SOC measurement — reused in module validator tests."""
    return {
        "soc": Measurement(
            unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
        )
    }


# --- Enum sanity ---


def test_enum_values() -> None:
    assert TemplateKind.LEAF == "leaf"
    assert TemplateKind.MODULE == "module"
    assert Publisher.LINE_CONTROLLER == "line_controller"
    assert Publisher.ANALYST == "analyst"
    assert Fanout.LINE_CONTROLLER == "line_controller"


# --- DeviceTemplate happy paths ---


def test_device_template_leaf_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="revenue_meter",
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


def test_device_template_module_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="bess_module",
        kind=TemplateKind.MODULE,
        description="BESS module aggregation",
        contains=[ContainsEntry(template="bess_rack", qty="scalable")],
        measurements={
            "state_of_charge": Measurement(
                unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
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
            template="Revenue-Meter",  # uppercase + dash → invalid
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            description="test",
            measurements=_mv(),
        )


# --- Kind-vs-equipment_id validators ---


def test_device_template_leaf_requires_equipment_id() -> None:
    with pytest.raises(ValidationError, match="equipment_id required"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id=None,
            description="test",
            measurements=_mv(),
        )


def test_device_template_module_rejects_equipment_id() -> None:
    with pytest.raises(ValidationError, match="equipment_id forbidden"):
        DeviceTemplate(
            template="bess_module",
            kind=TemplateKind.MODULE,
            equipment_id="GRD-MTR-001",
            description="test",
            contains=[],
            measurements=_ms(),
        )


# --- Must-have-channels validator ---


def test_device_template_must_declare_measurements_or_commands() -> None:
    with pytest.raises(ValidationError, match="must declare at least one"):
        DeviceTemplate(
            template="empty",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            vendor="Acme",
            model="X1",
            description="test",
        )


# --- Leaf vendor/model required; module vendor/model forbidden ---


def test_device_template_leaf_requires_vendor_and_model() -> None:
    with pytest.raises(ValidationError, match="vendor required"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            model="ION9000",
            description="test",
            measurements=_mv(),
        )
    with pytest.raises(ValidationError, match="model required"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            vendor="Schneider",
            description="test",
            measurements=_mv(),
        )


def test_device_template_module_rejects_vendor_and_model() -> None:
    with pytest.raises(ValidationError, match="vendor forbidden"):
        DeviceTemplate(
            template="bess_module",
            kind=TemplateKind.MODULE,
            vendor="Acme",
            description="test",
            measurements=_ms(),
        )
    with pytest.raises(ValidationError, match="model forbidden"):
        DeviceTemplate(
            template="bess_module",
            kind=TemplateKind.MODULE,
            model="X1",
            description="test",
            measurements=_ms(),
        )


# --- Leaf rejects contains ---


def test_device_template_leaf_rejects_contains() -> None:
    with pytest.raises(ValidationError, match="contains forbidden"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            vendor="Schneider",
            model="ION9000",
            description="test",
            contains=[ContainsEntry(template="sub_module", qty=1)],
            measurements=_mv(),
        )

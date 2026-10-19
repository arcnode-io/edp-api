"""Leaf vs module rules: equipment id, vendor/model, contains, channels."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    ContainsEntry,
    DeviceTemplate,
    TemplateKind,
)
from src.shared.schemas.template_test_support import (
    _mv,
    _ms,
)

# --- Kind-vs-equipment_id validators ---


def test_device_template_leaf_requires_equipment_id() -> None:
    with pytest.raises(ValidationError, match="equipment_id required"):
        DeviceTemplate(
            template="poi_meter",
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


def test_module_template_must_declare_measurements_or_commands() -> None:
    with pytest.raises(ValidationError, match="must declare at least one"):
        DeviceTemplate(
            template="empty_module",
            kind=TemplateKind.MODULE,
            description="test",
            contains=[ContainsEntry(template="poi_meter", qty=1)],
        )


def test_leaf_template_without_channels_is_passive() -> None:
    # Arrange / Act — e.g. switchgear: drawn on the SLD, never polled
    t = DeviceTemplate(
        template="switchgear",
        kind=TemplateKind.LEAF,
        equipment_id="GRD-SWG-001",
        vendor="ABB",
        model="SafeGear",
        description="test",
    )
    # Assert
    assert t.measurements == {}
    assert t.commands == {}


# --- Leaf vendor/model required; module vendor/model forbidden ---


def test_device_template_leaf_requires_vendor_and_model() -> None:
    with pytest.raises(ValidationError, match="vendor required"):
        DeviceTemplate(
            template="poi_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            model="ION9000",
            description="test",
            measurements=_mv(),
        )
    with pytest.raises(ValidationError, match="model required"):
        DeviceTemplate(
            template="poi_meter",
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
            template="poi_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            vendor="Schneider",
            model="ION9000",
            description="test",
            contains=[ContainsEntry(template="sub_module", qty=1)],
            measurements=_mv(),
        )

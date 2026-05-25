"""Alarm mirror-model tests — must parse the same shape as edp-module-assemblies."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.shared.schemas.alarm import (
    Alarm,
    AlarmPriority,
    AnalogThresholdSource,
    DiscreteRegisterSource,
    DnpEventSource,
    RedfishEventSource,
    Reset,
    SnmpTrapSource,
    load_alarms_from_spec,
)

EDP_MODULE_ASSEMBLIES = Path.home() / "arcnode" / "edp-module-assemblies"


def _alarm_dict(condition_source: dict) -> dict:
    return {
        "id": "test_alarm",
        "description": "test alarm",
        "condition_source": condition_source,
        "priority": "P2",
        "operator_action": "do the thing",
        "on_delay_ms": 100,
        "off_delay_ms": 0,
        "reset": "latched",
        "reference_doc": "TEST-001 manual §1",
    }


def test_discriminator_routes_to_each_of_five_variants() -> None:
    # Arrange / Act / Assert — one round-trip per variant
    variants: list[tuple[dict, type]] = [
        (
            {"type": "discrete_register", "address": 1, "meaning_when_set": "alarm"},
            DiscreteRegisterSource,
        ),
        (
            {
                "type": "analog_threshold",
                "address": 2,
                "threshold": 55.0,
                "direction": "above",
                "unit": "celsius",
            },
            AnalogThresholdSource,
        ),
        ({"type": "snmp_trap", "oid": "1.3.6.1.4.1.1718"}, SnmpTrapSource),
        (
            {"type": "dnp_event", "point_index": 10, "point_type": "binary_input"},
            DnpEventSource,
        ),
        ({"type": "redfish_event", "event_id": "PumpFault"}, RedfishEventSource),
    ]
    for cs, expected_type in variants:
        alarm = Alarm.model_validate(_alarm_dict(cs))
        assert isinstance(alarm.condition_source, expected_type)


def test_priority_and_reset_enums() -> None:
    # Arrange
    raw = _alarm_dict(
        {"type": "discrete_register", "address": 1, "meaning_when_set": "alarm"}
    )
    raw["priority"] = "P1"
    raw["reset"] = "auto"

    # Act
    alarm = Alarm.model_validate(raw)

    # Assert
    assert alarm.priority == AlarmPriority.P1
    assert alarm.reset == Reset.AUTO


def test_extra_field_rejected() -> None:
    # Arrange
    raw = _alarm_dict(
        {"type": "discrete_register", "address": 1, "meaning_when_set": "alarm"}
    )
    raw["sneaky"] = "extra"

    # Act / Assert
    with pytest.raises(ValidationError):
        Alarm.model_validate(raw)


@pytest.mark.skipif(
    not (EDP_MODULE_ASSEMBLIES / "equipment" / "GRD-SWG-001" / "spec.yaml").exists(),
    reason="requires edp-module-assemblies sibling checkout",
)
@pytest.mark.parametrize(
    "equipment_id",
    ["GRD-SWG-001", "EXT-BESS-002", "CMP-CDU-001"],
)
def test_edp_module_assemblies_pilot_specs_parse(equipment_id: str) -> None:
    """The pilot spec.yaml files from edp-module-assemblies parse with this mirror.

    Cross-repo contract verification — if the two Pydantic implementations
    diverge, this test catches the drift at edp-api CI time.
    """
    # Arrange
    spec_path = EDP_MODULE_ASSEMBLIES / "equipment" / equipment_id / "spec.yaml"
    spec_dict = yaml.safe_load(spec_path.read_text())

    # Act
    alarms = load_alarms_from_spec(spec_dict)

    # Assert
    assert len(alarms) >= 1

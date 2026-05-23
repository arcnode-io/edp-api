"""CableHoseScheduleService unit tests — derives cable + hose lists from DTM."""

import json as _json
from io import BytesIO

import pytest
from openpyxl import load_workbook

from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.cable_hose_schedule.cable_hose_schedule_service import (
    CableHoseScheduleService,
    serialize_cable_hose_schedule_xlsx,
)
from src.drawing.conftest import make_device, make_dtm
from src.shared.schemas.dtm import Dtm
from src.shared.schemas.measurement import Measurement
from src.shared.schemas.template import DeviceTemplate, TemplateKind
from src.shared.schemas.template_protocols import (
    Dnp3Binding,
    ModbusBinding,
    RedfishBinding,
)


def _tpl(
    slug: str, binding: ModbusBinding | Dnp3Binding | RedfishBinding
) -> DeviceTemplate:
    return DeviceTemplate(
        template=slug,
        kind=TemplateKind.LEAF,
        equipment_id=f"EXT-{slug.upper()}-001",
        vendor="V",
        model="M",
        description=slug,
        measurements={
            "power": Measurement(unit="watts", type="float", binding=binding)
        },
    )


@pytest.fixture
def three_protocol_dtm() -> Dtm:
    """3 devices on 3 different protocols — each yields one comms cable."""
    return make_dtm(
        devices={
            "switchgear_1": make_device("switchgear_1", template="switchgear"),
            "relay_1": make_device("relay_1", template="protective_relay"),
            "gpu_node_1": make_device("gpu_node_1", template="gpu_node"),
        },
        templates={
            "switchgear": _tpl(
                "switchgear",
                ModbusBinding(protocol="modbus_tcp", function_code=3, address=0),
            ),
            "protective_relay": _tpl(
                "protective_relay",
                Dnp3Binding(
                    protocol="dnp3_tcp", point_index=0, point_type="analog_input"
                ),
            ),
            "gpu_node": _tpl(
                "gpu_node", RedfishBinding(protocol="redfish", uri="/redfish/v1")
            ),
        },
    )


def test_generate_returns_cable_hose_schedule(three_protocol_dtm: Dtm) -> None:
    """generate() returns a CableHoseSchedule Pydantic object."""
    # Act
    actual = CableHoseScheduleService().generate(three_protocol_dtm)

    # Assert
    assert isinstance(actual, CableHoseSchedule)


def test_one_cable_per_bound_device(three_protocol_dtm: Dtm) -> None:
    """Every device with a Binding gets one comms cable row."""
    # Act
    schedule = CableHoseScheduleService().generate(three_protocol_dtm)

    # Assert
    assert len(schedule.cables) == 3
    device_ids = {c.from_device for c in schedule.cables}
    assert device_ids == set(three_protocol_dtm.devices)


def test_cable_carries_protocol_specific_type(three_protocol_dtm: Dtm) -> None:
    """Cable `cable_type` reflects the protocol (e.g. Modbus TCP → Cat6)."""
    # Act
    schedule = CableHoseScheduleService().generate(three_protocol_dtm)
    by_device = {c.from_device: c for c in schedule.cables}

    # Assert
    assert "Cat6" in by_device["switchgear_1"].cable_type
    assert "Cat6" in by_device["relay_1"].cable_type
    assert "Cat6" in by_device["gpu_node_1"].cable_type


def test_json_serialization_round_trips(three_protocol_dtm: Dtm) -> None:
    """`model_dump_json` produces parseable JSON with cables[] + metadata."""
    # Act
    schedule = CableHoseScheduleService().generate(three_protocol_dtm)
    body = _json.loads(schedule.model_dump_json())

    # Assert
    assert body["deployment_uuid"] == str(three_protocol_dtm.deployment_uuid)
    assert "generated_at" in body
    assert len(body["cables"]) == 3
    assert body["hoses"] == []


def test_xlsx_serializer_opens_with_cables_sheet(three_protocol_dtm: Dtm) -> None:
    """xlsx round-trips through openpyxl with a 'Cables' sheet of the right size."""
    # Act
    schedule = CableHoseScheduleService().generate(three_protocol_dtm)
    xlsx = serialize_cable_hose_schedule_xlsx(schedule)
    wb = load_workbook(BytesIO(xlsx))

    # Assert
    assert "Cables" in wb.sheetnames
    cables_ws = wb["Cables"]
    # Header row + one row per cable.
    assert cables_ws.max_row == 1 + 3


def test_xlsx_has_hoses_sheet_even_when_empty(three_protocol_dtm: Dtm) -> None:
    """`Hoses` sheet exists with the header row even when DTM has no liquid buses.

    v1 doesn't model liquid buses; hoses become derivable when the bus
    schema grows a `liquid` type. The empty sheet is the explicit signal
    to a reviewer that hose derivation is on the roadmap.
    """
    # Act
    schedule = CableHoseScheduleService().generate(three_protocol_dtm)
    xlsx = serialize_cable_hose_schedule_xlsx(schedule)
    wb = load_workbook(BytesIO(xlsx))

    # Assert
    assert "Hoses" in wb.sheetnames
    hoses_ws = wb["Hoses"]
    assert hoses_ws.max_row == 1  # header row only

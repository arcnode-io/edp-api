"""cable_hose_lines: cable + hose schedule rolled up into BOM lines."""

from datetime import UTC, datetime
from uuid import uuid4

from src.bom_generator.cable_hose_lines import cable_hose_lines
from src.cable_hose_schedule.cable_hose_schedule_models import (
    CableEntry,
    CableHoseSchedule,
    HoseEntry,
)


def _cable(tag: str, cable_type: str) -> CableEntry:
    return CableEntry(
        tag=tag,
        service="Comms - Modbus TCP",
        from_device="pdu_1",
        from_port="TCP/502",
        to_device="network_switch_1",
        to_port="eth1",
        cable_type=cable_type,
    )


def test_runs_roll_up_into_one_line_per_cable_or_hose_type() -> None:
    # Arrange
    hose = HoseEntry(
        tag="HOS-0001",
        service="Coolant Supply",
        from_device="cdu_1",
        from_port="supply",
        to_device="gpu_node_1",
        to_port="inlet",
        hose_type="EPDM 1in PG/W rated",
    )
    schedule = CableHoseSchedule(
        deployment_uuid=uuid4(),
        generated_at=datetime.now(UTC),
        cables=[_cable("CBL-0001", "Cat6 STP"), _cable("CBL-0002", "Cat6 STP")],
        hoses=[hose],
    )

    # Act
    lines = cable_hose_lines(schedule)

    # Assert — lengths are field-measured, so qty counts runs
    actual = {li.part_number: li.qty for li in lines}
    assert actual == {"Cat6 STP": 2, "EPDM 1in PG/W rated": 1}

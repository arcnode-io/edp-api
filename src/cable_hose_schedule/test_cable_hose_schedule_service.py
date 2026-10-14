"""Cable + hose schedule: every run matches the SLD, comms and P&ID.

Fixture: two compute containers and one grid container laid out like the
real equipment lists, plus the customer's battery, with the real template
catalog (so contains/power_from are the shipped ones).
"""

import json
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from openpyxl import load_workbook

from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.cable_hose_schedule.cable_hose_schedule_service import (
    CableHoseScheduleService,
    serialize_cable_hose_schedule_xlsx,
)
from src.dtm.template_loader import TemplateLoader
from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    Connection,
    Device,
    Dtm,
    SizingParams,
)

_TBD = PROVISIONED_AT_COMMISSIONING
_COMPUTE: list[tuple[str, str, bool]] = [
    ("rack", "RACK-1", False),
    ("panelboard", "PNL-1", False),
    *[("gpu_node", f"NODE-{i}", True) for i in range(1, 8)],
    ("cdu", "CDU-1", True),
    ("network_switch", "SW-DATA-1", True),
    ("mgmt_switch", "SW-MGMT-1", False),
    *[("pdu", f"PDU-{p}{i}", True) for p in "AB" for i in range(1, 4)],
    ("dc_external", "DC-1", True),
]
_GRID: list[tuple[str, str, bool]] = [
    ("switchgear", "SWG-1", False),
    ("protective_relay", "RLY-1", True),
    ("transformer", "T1", False),
    ("lv_switchboard", "SWBD-1", False),
    ("grid_mgmt_switch", "SW-MGMT-1", False),
    ("poi_meter", "MTR-POI", True),
]


def _site() -> Dtm:
    devices: dict[str, Device] = {}
    count: dict[str, int] = {}

    def add(template: str, tag: str, parent: str | None, polled: bool) -> str:
        count[template] = count.get(template, 0) + 1
        did = f"{template}_{count[template]}"
        conn = Connection(host=_TBD, port=_TBD) if polled else None
        devices[did] = Device(
            device_id=did,
            template=template,
            parent=parent,
            display_name=tag,
            connection=conn,
        )
        return did

    for c in (1, 2):
        module = add("compute_module", f"C{c}", None, False)
        for template, tag, polled in _COMPUTE:
            add(template, f"C{c}-{tag}", module, polled)
    grid = add("grid_module", "G1", None, False)
    for template, tag, polled in _GRID:
        add(template, f"G1-{tag}", grid, polled)
    bess = add("bess_module", "BESS", None, False)
    add("bess_rack", "BESS-1", bess, True)

    catalog = TemplateLoader(
        root=Path(__file__).resolve().parents[2] / "device_templates"
    ).load_catalog()
    return Dtm(
        deployment_uuid=UUID("00000000-0000-0000-0000-000000000046"),
        sizing_params=SizingParams(
            P_compute_total_kW=172.0, E_BESS_total_kWh=1000.0, T_coolant_setpoint_C=30.0
        ),
        devices=devices,
        buses=[],
        templates_used={t: catalog[t] for t in {d.template for d in devices.values()}},
    )


@pytest.fixture
def schedule() -> CableHoseSchedule:
    return CableHoseScheduleService().generate(_site())


def _runs(entries: list, service_prefix: str) -> set[tuple[str, str]]:
    return {
        (e.from_device, e.to_device)
        for e in entries
        if e.service.startswith(service_prefix)
    }


def test_polled_devices_cable_to_their_own_containers_management_switch(
    schedule: CableHoseSchedule,
) -> None:
    # Act
    comms = _runs(schedule.cables, "Comms")

    # Assert — ADR-019
    assert ("C2-NODE-1", "C2-SW-MGMT-1") in comms
    assert ("G1-RLY-1", "G1-SW-MGMT-1") in comms
    assert ("BESS-1", "G1-SW-MGMT-1") in comms


def test_compute_management_switches_uplink_to_g1_over_fiber(
    schedule: CableHoseSchedule,
) -> None:
    # Act
    uplinks = {
        (e.from_device, e.to_device, e.cable_type)
        for e in schedule.cables
        if e.service.startswith("Comms - management uplink")
    }

    # Assert
    fiber = "Single-mode fiber pair, LC duplex"
    assert {
        ("C1-SW-MGMT-1", "G1-SW-MGMT-1", fiber),
        ("C2-SW-MGMT-1", "G1-SW-MGMT-1", fiber),
    } <= uplinks
    assert ("G1-SW-MGMT-1", "EMS-GW", "Cat6 STP") in uplinks


def test_power_runs_follow_the_one_line(schedule: CableHoseSchedule) -> None:
    # Act
    power = _runs(schedule.cables, "Power")

    # Assert — grid switchboard feeds each compute panelboard (ADR-018), the
    # panelboard feeds PDUs, CDU and dry cooler, and every node is fed from
    # both an A and a B PDU (ADR-005)
    assert {("G1-SWBD-1", "C1-PNL-1"), ("G1-SWBD-1", "C2-PNL-1")} <= power
    assert {
        ("C1-PNL-1", "C1-PDU-A1"),
        ("C1-PNL-1", "C1-CDU-1"),
        ("C1-PNL-1", "C1-DC-1"),
    } <= power
    node_feeds = {src for src, dst in power if dst == "C1-NODE-4"}
    assert {s.removeprefix("C1-")[:5] for s in node_feeds} == {"PDU-A", "PDU-B"}


def test_cdu_primary_loop_runs_to_its_own_dry_cooler(
    schedule: CableHoseSchedule,
) -> None:
    # Act
    hoses = _runs(schedule.hoses, "Coolant")

    # Assert — matches P&ID sheet 2; secondary loop per node plate (sheet 1)
    assert {("C1-DC-1", "C1-CDU-1"), ("C1-CDU-1", "C1-DC-1")} <= hoses
    assert ("C2-CDU-1", "C2-NODE-7") in hoses


def test_every_run_ends_on_a_real_device_or_a_named_site_item(
    schedule: CableHoseSchedule,
) -> None:
    # Arrange
    tags = {d.display_name for d in _site().devices.values()} | {"EMS-GW"}

    # Act
    ends = {
        e
        for r in [*schedule.cables, *schedule.hoses]
        for e in (r.from_device, r.to_device)
    }

    # Assert
    assert ends - tags == set()


def test_json_and_xlsx_serialize(schedule: CableHoseSchedule) -> None:
    # Act
    reloaded = CableHoseSchedule.model_validate(json.loads(schedule.model_dump_json()))
    wb = load_workbook(BytesIO(serialize_cable_hose_schedule_xlsx(schedule)))

    # Assert
    assert reloaded == schedule
    assert wb.sheetnames == ["Cables", "Hoses"]

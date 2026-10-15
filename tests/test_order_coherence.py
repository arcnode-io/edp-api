"""Every artifact matches the order and each other (QA 2026-10-13).

Runs real orders against the real assemblies data and checks the
package the way a design reviewer would: the order reaches the hardware,
the BOM and the device data list the same devices, every device has
install steps and every polled device a comms run, and every tag is unique.
"""

from collections import Counter

import pytest

from src.bom_generator.bom_models import Bom, ProcurementPath
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.drawing.install_sequence_service import build_mop_rows
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.dtm import Dtm
from tests.assemblies_checkout import REPO
from tests.order_packages import NODE_FOR_GPU, ORDERS, package_for

pytestmark = pytest.mark.skipif(
    not (REPO / "manifest.yaml").is_file(),
    reason="edp-module-assemblies checkout required",
)


@pytest.fixture(scope="module", params=sorted(ORDERS))
def package(
    request: pytest.FixtureRequest,
) -> tuple[ConfiguratorPayload, Bom, Dtm, CableHoseSchedule]:
    return package_for(ORDERS[request.param])


def test_the_order_reaches_the_hardware(package: tuple) -> None:
    # Arrange
    payload, bom, _, _ = package

    # Act
    nodes = {
        li.equipment_id
        for li in bom.line_items
        if (li.equipment_id or "").startswith("CMP-NODE")
    }
    bess = [li for li in bom.line_items if li.ref_des == "BESS-1"]

    # Assert — the ordered GPU's node, and the ordered battery size
    assert nodes == {NODE_FOR_GPU[payload.gpu_variant.value]}
    assert f"{payload.bess_capacity_mwh:g} MWh" in bess[0].description
    assert bom.order.gpus_requested == payload.target_gpu_count


def test_bom_and_device_data_list_the_same_devices(package: tuple) -> None:
    # Arrange
    _, bom, dtm, _ = package
    bought = (ProcurementPath.CATALOG, ProcurementPath.ENGINEERED_TO_ORDER)

    # Act — qty per equipment on both sides (the customer's battery included)
    in_bom: Counter[str] = Counter()
    for li in bom.line_items:
        if li.equipment_id and li.procurement_path in bought:
            in_bom[li.equipment_id] += li.qty
    in_dtm = Counter(
        dtm.templates_used[d.template].equipment_id
        for d in dtm.devices.values()
        if d.parent is not None and not d.template.startswith("bess")
    )

    # Assert
    assert in_bom == in_dtm
    assert any(d.display_name == "BESS-1" for d in dtm.devices.values())


def test_every_device_has_install_steps(package: tuple) -> None:
    # Arrange
    _, _, dtm, _ = package
    leaves = {d.display_name for d in dtm.devices.values() if d.parent is not None}

    # Act
    stepped = {row.device for row in build_mop_rows(dtm)}

    # Assert
    assert leaves - stepped == set()


def test_every_polled_device_has_a_comms_run_and_every_run_lands(
    package: tuple,
) -> None:
    # Arrange
    _, _, dtm, schedule = package
    tags = {d.display_name for d in dtm.devices.values()} | {"EMS-GW"}
    polled = {d.display_name for d in dtm.devices.values() if d.connection is not None}

    # Act
    comms_from = {
        c.from_device for c in schedule.cables if c.service.startswith("Comms")
    }
    ends = {
        e
        for r in [*schedule.cables, *schedule.hoses]
        for e in (r.from_device, r.to_device)
    }

    # Assert
    assert (polled - comms_from, ends - tags) == (set(), set())


def test_every_tag_names_one_device(package: tuple) -> None:
    # Arrange
    _, _, dtm, _ = package

    # Act
    repeated = [
        t
        for t, n in Counter(d.display_name for d in dtm.devices.values()).items()
        if n > 1
    ]

    # Assert
    assert repeated == []


def test_dc_ext_pcs_sits_on_the_battery_pad() -> None:
    # Arrange — ADR-022: one CAB1000 per grid container, under the battery
    _, bom, dtm, _ = package_for(ORDERS["600xB200-4MWh-dc_ext"])
    battery = next(
        d.device_id for d in dtm.devices.values() if d.display_name == "BESS"
    )

    # Act
    pcs = [d for d in dtm.devices.values() if d.template == "pcs"]
    lines = [li for li in bom.line_items if li.equipment_id == "GRD-PCS-001"]

    # Assert
    assert [d.parent for d in pcs] == [battery] * bom.grid_container_qty
    assert [(li.section.value, li.qty) for li in lines] == [
        ("site_and_interfaces", bom.grid_container_qty)
    ]

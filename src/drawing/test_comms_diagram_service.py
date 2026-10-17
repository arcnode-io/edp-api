"""CommsDiagramService: site management network + typical compute container."""

import io
import re
from datetime import UTC, datetime
from uuid import UUID

import ezdxf
from ezdxf.entities import Text

from src.bom_generator.bom_test_support import ORDER
from src.bom_generator.bom_models import Bom
from src.drawing.comms_diagram_service import (
    CommsDiagramOutputs,
    CommsDiagramService,
)
from src.drawing.conftest import make_dtm, make_template
from src.shared.schemas.dtm import PROVISIONED_AT_COMMISSIONING, Connection, Device

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000043")

# (device_id, template, parent) — two compute containers + one grid container
_DEVICES: list[tuple[str, str, str | None]] = [
    ("compute_module_1", "compute_module", None),
    ("gpu_node_1", "gpu_node", "compute_module_1"),
    ("pdu_1", "pdu", "compute_module_1"),
    ("compute_module_2", "compute_module", None),
    ("gpu_node_8", "gpu_node", "compute_module_2"),
    ("grid_module_1", "grid_module", None),
    ("protective_relay_1", "protective_relay", "grid_module_1"),
    ("bess_module_1", "bess_module", None),
    ("bess_rack_1", "bess_rack", "bess_module_1"),
]


def _device(device_id: str, template: str, parent: str | None) -> Device:
    tbd = PROVISIONED_AT_COMMISSIONING
    connection = None if parent is None else Connection(host=tbd, port=tbd)
    # Reason: gpu_node_1 carries a site tag like real DTMs; the rest don't,
    # to check the drawing falls back to the device id.
    tag = "C1-NODE-1" if device_id == "gpu_node_1" else None
    return Device(
        device_id=device_id,
        template=template,
        parent=parent,
        connection=connection,
        display_name=tag,
    )


def _comms(devices: dict[str, Device] | None = None) -> CommsDiagramOutputs:
    devices = devices or {d: _device(d, t, p) for d, t, p in _DEVICES}
    dtm = make_dtm(
        devices=devices,
        templates={d.template: make_template(d.template) for d in devices.values()},
    )
    bom = Bom(
        deployment_id=DEPLOYMENT_ID,
        profile="commercial_ac",
        manifest_version="0.0.0-test",
        generated_at=datetime.now(UTC),
        compute_container_qty=2,
        grid_container_qty=1,
        order=ORDER,
    )
    return CommsDiagramService().generate(dtm, bom=bom, profile="commercial_ac")


def _sheet_texts(outputs: CommsDiagramOutputs) -> tuple[str, str]:
    """(sheet 1 texts, sheet 2 texts) — sheet 2 sits right of x = 420."""
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))
    texts = [t for t in doc.modelspace().query("TEXT") if isinstance(t, Text)]
    left = " | ".join(t.dxf.text for t in texts if t.dxf.insert.x < 420)
    right = " | ".join(t.dxf.text for t in texts if t.dxf.insert.x >= 420)
    return left, right


def test_pdf_has_a_site_sheet_and_a_typical_compute_sheet() -> None:
    # Act
    outputs = _comms()

    # Assert
    assert len(re.findall(rb"/Type /Page\b", outputs.pdf)) == 2


def test_site_sheet_hangs_grid_devices_and_compute_uplinks_off_the_grid_switch() -> (
    None
):
    # Act
    site, _ = _sheet_texts(_comms())

    # Assert
    assert "EMS GATEWAY" in site
    assert "protective_relay_1" in site
    assert "bess_rack_1" in site  # the customer's battery, from the device data
    assert "C1-C2 MGMT SWITCH UPLINKS x2" in site


def test_compute_sheet_draws_the_first_container_as_typical() -> None:
    # Act
    _, compute = _sheet_texts(_comms())

    # Assert — container 1's devices only, addresses pending commissioning
    assert "C1-NODE-1" in compute
    assert "gpu_node_8" not in compute
    assert "ADDR TBD" in compute


def test_a_megapack_fleet_draws_as_one_box() -> None:
    # Arrange — a 10 MWh order is 3 Megapacks; one box each would crowd the
    # sheet as orders grow
    devices = {d: _device(d, t, p) for d, t, p in _DEVICES}
    for n in (1, 2, 3):
        rack = _device(f"bess_rack_{n}", "bess_rack", "bess_module_1")
        devices[rack.device_id] = rack.model_copy(
            update={"display_name": f"BESS-1-MP-{n}"}
        )

    # Act
    site, _ = _sheet_texts(_comms(devices))

    # Assert
    assert ("BESS-1-MP-1…3" in site, "BESS-1-MP-2" in site) == (True, False)

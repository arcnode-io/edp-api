"""Every sheet of every engineering drawing stays inside its drawing area.

Small and large orders, all three drawings. The DXF lays sheets left to
right SHEET_PITCH_MM apart; each entity is checked against its own sheet.
"""

import io
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import ezdxf
import pytest
from ezdxf import bbox
from ezdxf.entities import DXFGraphic

from src.bom_generator.bom_test_support import ORDER
from src.bom_generator.bom_models import Bom
from src.drawing._drawing_area import violations
from src.drawing._eng_render import SHEET_PITCH_MM
from src.drawing.comms_diagram_service import CommsDiagramService
from src.drawing.conftest import make_dtm, make_template
from src.drawing.pid_cooling_service import PidCoolingService
from src.drawing.sld_engineering_service import SldEngineeringService
from src.shared.schemas.dtm import Connection, Device, Dtm

_LEAVES: dict[str, int] = {"gpu_node": 7, "cdu": 1, "pdu": 6, "network_switch": 1}


def _dtm(compute_qty: int) -> Dtm:
    """compute_qty compute modules, each with its full set of leaves."""
    devices: dict[str, Device] = {}
    count: dict[str, int] = defaultdict(int)
    for c in range(1, compute_qty + 1):
        module = f"compute_module_{c}"
        devices[module] = Device(device_id=module, template="compute_module")
        for template, qty in _LEAVES.items():
            for _ in range(qty):
                count[template] += 1
                did = f"{template}_{count[template]}"
                devices[did] = Device(
                    device_id=did,
                    template=template,
                    parent=module,
                    connection=Connection(host="10.0.0.1", port=502),
                )
    devices["grid_module_1"] = Device(device_id="grid_module_1", template="grid_module")
    templates = {t: make_template(t) for t in {d.template for d in devices.values()}}
    return make_dtm(devices=devices, templates=templates)


def _bom(compute_qty: int, grid_qty: int) -> Bom:
    return Bom(
        deployment_id=UUID("00000000-0000-0000-0000-000000000044"),
        profile="commercial_ac",
        manifest_version="0.0.0-test",
        generated_at=datetime.now(UTC),
        compute_container_qty=compute_qty,
        grid_container_qty=grid_qty,
        order=ORDER,
    )


_DRAWINGS: dict[str, Callable[[Dtm, Bom], bytes]] = {
    "sld": lambda d, b: (
        SldEngineeringService().generate(d, bom=b, profile=b.profile).dxf
    ),
    "comms": lambda d, b: (
        CommsDiagramService().generate(d, bom=b, profile=b.profile).dxf
    ),
    "pid": lambda d, b: PidCoolingService().generate(d, profile=b.profile).dxf,
}


def _by_sheet(dxf: bytes) -> dict[int, list[DXFGraphic]]:
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8")))
    sheets: dict[int, list[DXFGraphic]] = defaultdict(list)
    for entity in doc.modelspace():
        box = bbox.extents([entity])
        if box.has_data:
            sheets[int(box.center.x // SHEET_PITCH_MM)].append(entity)
    return sheets


@pytest.mark.parametrize("drawing", sorted(_DRAWINGS))
@pytest.mark.parametrize(("compute_qty", "grid_qty"), [(1, 1), (20, 3)])
def test_no_element_enters_the_title_block_or_border(
    drawing: str, compute_qty: int, grid_qty: int
) -> None:
    # Arrange
    dxf = _DRAWINGS[drawing](_dtm(compute_qty), _bom(compute_qty, grid_qty))

    # Act
    actual = {
        sheet: violations(entities, dx=sheet * SHEET_PITCH_MM)
        for sheet, entities in _by_sheet(dxf).items()
    }

    # Assert
    assert {s: v for s, v in actual.items() if v} == {}

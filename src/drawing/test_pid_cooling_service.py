"""PidCoolingService: rack + facility coolant sheets, every pipe connected."""

import io
import math
from itertools import pairwise
import re

import ezdxf
import pytest
from ezdxf.document import Drawing
from ezdxf.entities import (
    Circle,
    DXFGraphic,
    Insert,
    Line,
    LWPolyline,
    MText,
    Text,
)
from ezdxf.layouts import Modelspace

from src.drawing._eng_render import SHEET_PITCH_MM
from src.drawing.conftest import make_dtm, make_template
from src.drawing.pid_cooling_service import PidCoolingOutputs, PidCoolingService
from src.shared.schemas.dtm import Device, Dtm

_TOL_MM = 0.05
Point = tuple[float, float]


def _device(
    device_id: str, template: str, parent: str | None, tag: str | None
) -> Device:
    return Device(
        device_id=device_id, template=template, parent=parent, display_name=tag
    )


@pytest.fixture
def two_containers() -> Dtm:
    """Two compute containers, each a CDU, 7 nodes and a dry cooler."""
    devices: dict[str, Device] = {}
    for c in (1, 2):
        module = f"compute_module_{c}"
        devices[module] = _device(module, "compute_module", None, f"C{c}")
        devices[f"cdu_{c}"] = _device(f"cdu_{c}", "cdu", module, f"C{c}-CDU-1")
        devices[f"dc_external_{c}"] = _device(
            f"dc_external_{c}", "dc_external", module, f"C{c}-DC-1"
        )
        for n in range(1, 8):
            i = (c - 1) * 7 + n
            devices[f"gpu_node_{i}"] = _device(
                f"gpu_node_{i}", "gpu_node", module, f"C{c}-NODE-{n}"
            )
    templates = {t: make_template(t) for t in {d.template for d in devices.values()}}
    return make_dtm(devices=devices, templates=templates)


def _doc(outputs: PidCoolingOutputs) -> Drawing:
    return ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))


def _texts(outputs: PidCoolingOutputs) -> str:
    msp = _doc(outputs).modelspace()
    return " | ".join(t.dxf.text for t in msp.query("TEXT") if isinstance(t, Text))


def test_pdf_has_a_rack_sheet_and_a_facility_sheet(two_containers: Dtm) -> None:
    # Act
    outputs = PidCoolingService().generate(two_containers)

    # Assert
    assert len(re.findall(rb"/Type /Page\b", outputs.pdf)) == 2


def test_rack_sheet_draws_the_first_container_as_typical(two_containers: Dtm) -> None:
    # Act
    texts = _texts(PidCoolingService().generate(two_containers))

    # Assert — C1's CDU and 7 node plates, labelled typical of both containers
    assert "C1-CDU-1" in texts
    assert "C1-NODE-7 DLC" in texts
    assert "C2-NODE-1" not in texts
    assert "COMPUTE CONTAINER C1-C2 (TYPICAL OF 2)" in texts


def test_title_block_carries_the_deployment_uuid(two_containers: Dtm) -> None:
    # Act
    msp = _doc(PidCoolingService().generate(two_containers)).modelspace()

    # Assert
    blob = " ".join(m.text for m in msp.query("MTEXT") if isinstance(m, MText))
    assert str(two_containers.deployment_uuid) in blob


def test_no_pipe_ends_in_mid_air(two_containers: Dtm) -> None:
    # Arrange — every open end of a process line (pipe or symbol port stub)
    # must land on another process element: a pipe, a symbol outline, a
    # pump circle or an off-sheet connector.
    msp = _doc(PidCoolingService().generate(two_containers)).modelspace()

    # Act
    dangling = _dangling_ends(msp)

    # Assert
    assert dangling == []


def _dangling_ends(msp: Modelspace) -> list[tuple[int, Point]]:
    """(sheet, point) for every open line end that touches nothing else."""
    parts = [
        p
        for e in msp.query("*[layer=='PROCESS']")
        if isinstance(e, DXFGraphic)
        for p in _primitives(e)
    ]
    dangling = []
    for i, (kind, geom) in enumerate(parts):
        if kind != "line":
            continue
        for end in geom:
            touched = any(j != i and _touches(end, parts[j]) for j in range(len(parts)))
            if not touched:
                dangling.append((int(end[0] // SHEET_PITCH_MM), end))
    return dangling


def _primitives(entity: DXFGraphic) -> list[tuple[str, tuple]]:
    """Flatten an entity (and block contents) to lines, closed edges, circles."""
    match entity:
        case Insert():
            return [p for v in entity.virtual_entities() for p in _primitives(v)]
        case Line():
            s, e = entity.dxf.start, entity.dxf.end
            return [("line", ((s.x, s.y), (e.x, e.y)))]
        case LWPolyline():
            pts = [(p[0], p[1]) for p in entity.get_points("xy")]
            if entity.closed:
                pts.append(pts[0])
                return [("edge", (a, b)) for a, b in pairwise(pts)]
            return [("line", (a, b)) for a, b in pairwise(pts)]
        case Circle():
            c = entity.dxf.center
            return [("circle", ((c.x, c.y), entity.dxf.radius))]
        case _:
            return []


def _touches(p: Point, part: tuple[str, tuple]) -> bool:
    kind, geom = part
    if kind == "circle":
        (cx, cy), r = geom
        return abs(math.dist(p, (cx, cy)) - r) <= _TOL_MM
    a, b = geom
    return _on_segment(p, a, b)


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    ab = math.dist(a, b)
    if ab == 0:
        return math.dist(p, a) <= _TOL_MM
    return abs(math.dist(a, p) + math.dist(p, b) - ab) <= _TOL_MM

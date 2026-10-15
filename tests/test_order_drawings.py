"""The compute-container drawings show the ordered hardware (QA 2026-10-15).

The SLD and comms typical sheets are drawn from container C1 and the BOM.
Each real order must show its own server and dry cooler, and C1's networked
devices, whatever the GPU variant or context.
"""

import io

import ezdxf
import pytest
from ezdxf.entities import Text

from src.drawing.comms_diagram_service import CommsDiagramService
from src.drawing.sld_engineering_service import SldEngineeringService
from tests.assemblies_checkout import REPO
from tests.order_packages import NODE_FOR_GPU, ORDERS, package_for

pytestmark = pytest.mark.skipif(
    not (REPO / "manifest.yaml").is_file(),
    reason="edp-module-assemblies checkout required",
)


def _texts(dxf: bytes) -> str:
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8")))
    return " | ".join(
        t.dxf.text for t in doc.modelspace().query("TEXT") if isinstance(t, Text)
    )


@pytest.mark.parametrize("order", sorted(ORDERS))
def test_compute_sheets_show_the_ordered_hardware(order: str) -> None:
    # Arrange
    payload, bom, dtm, _ = package_for(ORDERS[order])
    profile = bom.profile
    node = NODE_FOR_GPU[payload.gpu_variant.value]
    defense = payload.deployment_context.value == "defense_forward"
    cooler = "EXT-DC-002" if defense else "EXT-DC-001"

    # Act
    sld = _texts(SldEngineeringService().generate(dtm, bom=bom, profile=profile).dxf)
    comms = _texts(CommsDiagramService().generate(dtm, bom=bom, profile=profile).dxf)

    # Assert — the ordered node and cooler, never a missing part, and C1's
    # nodes on the management network
    assert [node in sld, cooler in sld, node in comms, "PART TBD" in sld + comms] == [
        True,
        True,
        True,
        False,
    ]
    assert "C1-NODE-1" in comms

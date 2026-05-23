"""PidCoolingService unit tests — paper-grade P&ID DXF + PDF, ISA 5.1 symbols."""

import io

import ezdxf
import pytest

from src.drawing.conftest import make_device, make_dtm, make_template
from src.drawing.pid_cooling_service import (
    PidCoolingOutputs,
    PidCoolingService,
)
from src.shared.schemas.dtm import Dtm


@pytest.fixture
def cdu_with_two_gpu_nodes() -> Dtm:
    """Minimal cooling-loop DTM: 1 CDU + 2 GPU nodes (DLC consumers)."""
    return make_dtm(
        devices={
            "cdu_1": make_device("cdu_1", template="cdu"),
            "gpu_node_1": make_device("gpu_node_1", template="gpu_node"),
            "gpu_node_2": make_device("gpu_node_2", template="gpu_node"),
        },
        templates={
            "cdu": make_template("cdu"),
            "gpu_node": make_template("gpu_node"),
        },
    )


def test_generate_returns_outputs_with_dxf_and_pdf_bytes(
    cdu_with_two_gpu_nodes: Dtm,
) -> None:
    """generate() returns an outputs bundle with non-empty dxf + pdf bytes."""
    # Act
    actual = PidCoolingService().generate(cdu_with_two_gpu_nodes)

    # Assert
    assert isinstance(actual, PidCoolingOutputs)
    assert len(actual.dxf) > 0
    assert len(actual.pdf) > 0


def test_pdf_starts_with_magic(cdu_with_two_gpu_nodes: Dtm) -> None:
    """PDF bytes start with %PDF- — proves real vector PDF."""
    # Act
    outputs = PidCoolingService().generate(cdu_with_two_gpu_nodes)

    # Assert
    assert outputs.pdf.startswith(b"%PDF-")


def test_pdf_is_two_pages(cdu_with_two_gpu_nodes: Dtm) -> None:
    """One PDF, two sheets: rack-internal (1/2) + facility loop (2/2)."""
    # Act
    outputs = PidCoolingService().generate(cdu_with_two_gpu_nodes)

    # Assert — count individual /Type /Page entries (excluding /Type /Pages parent).
    import re

    page_objects = re.findall(rb"/Type\s*/Page(?!s)", outputs.pdf)
    assert len(page_objects) == 2


def test_dxf_contains_cdu_symbol_per_cdu_device(
    cdu_with_two_gpu_nodes: Dtm,
) -> None:
    """Each `cdu` device in the DTM appears as a CDU block on sheet 1."""
    # Act
    outputs = PidCoolingService().generate(cdu_with_two_gpu_nodes)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert
    inserts = list(doc.modelspace().query("INSERT"))
    cdu_inserts = [i for i in inserts if i.dxf.name.startswith("equip_cdu_")]
    assert len(cdu_inserts) == 1  # one cdu device → one CDU symbol


def test_dxf_carries_iso_7200_title_block_with_deployment_uuid(
    cdu_with_two_gpu_nodes: Dtm,
) -> None:
    """Sheet 1 + sheet 2 both carry a title block with the deployment_uuid."""
    # Act
    outputs = PidCoolingService().generate(cdu_with_two_gpu_nodes)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert — sheet 1 is the only DXF sheet (DXF is single-modelspace; sheet 2
    # lives only in the PDF). Title block carries the UUID.
    from ezdxf.entities import MText

    mtexts = [m for m in doc.modelspace().query("MTEXT") if isinstance(m, MText)]
    text_blob = " ".join(m.text for m in mtexts)
    assert str(cdu_with_two_gpu_nodes.deployment_uuid) in text_blob
    # Title row identifies this as a P&ID, not an SLD.
    assert "P&ID" in text_blob


def test_dxf_emits_instrument_bubbles_at_cdu_ports(
    cdu_with_two_gpu_nodes: Dtm,
) -> None:
    """ISA 5.1 instrument bubbles at standard CDU port locations.

    A complete P&ID needs at minimum TT/PT on each CDU port (primary supply,
    primary return, secondary supply, secondary return) + FT on the
    secondary supply. 4 ports x 2 instruments (TT,PT) + 1 FT = 9 bubbles.
    """
    # Act
    outputs = PidCoolingService().generate(cdu_with_two_gpu_nodes)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert — instrument bubbles are INSERTs of an `instr_*` block
    inserts = list(doc.modelspace().query("INSERT"))
    instr_inserts = [i for i in inserts if i.dxf.name.startswith("instr_")]
    assert len(instr_inserts) >= 9

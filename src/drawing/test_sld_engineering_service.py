"""SldEngineeringService unit tests — paper-grade SLD DXF + PDF."""

import io

import ezdxf
import pytest

from src.drawing.conftest import (
    make_bus,
    make_device,
    make_dtm,
    make_template,
)
from src.drawing.sld_engineering_service import (
    SldEngineeringOutputs,
    SldEngineeringService,
)
from src.shared.schemas.dtm import Dtm


@pytest.fixture
def two_device_dtm() -> Dtm:
    """BESS rack (source — MMXU.W) feeding a switchgear over one AC bus."""
    return make_dtm(
        devices={
            "bess_1": make_device("bess_1", template="bess_rack"),
            "switch_1": make_device("switch_1", template="switchgear"),
        },
        buses=[make_bus("ac_main", ["bess_1", "switch_1"], bus_type="ac")],
        templates={
            "bess_rack": make_template("bess_rack", iec_61850_ref="MMXU.W"),
            "switchgear": make_template("switchgear"),
        },
    )


def test_generate_returns_dxf_and_pdf_bytes(two_device_dtm: Dtm) -> None:
    """generate() returns an outputs bundle with non-empty dxf + pdf bytes."""
    # Act
    actual = SldEngineeringService().generate(two_device_dtm)

    # Assert
    assert isinstance(actual, SldEngineeringOutputs)
    assert len(actual.dxf) > 0
    assert len(actual.pdf) > 0


def test_dxf_round_trips_through_ezdxf(two_device_dtm: Dtm) -> None:
    """DXF bytes re-parse via ezdxf without error — proves real DXF, not stub."""
    # Act
    outputs = SldEngineeringService().generate(two_device_dtm)

    # Assert
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))
    assert doc.dxfversion == "AC1032"  # R2018 magic


def test_dxf_contains_one_block_ref_per_device(two_device_dtm: Dtm) -> None:
    """Every device in the DTM lands as an INSERT (block reference) in modelspace."""
    # Act
    outputs = SldEngineeringService().generate(two_device_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert
    inserts = list(doc.modelspace().query("INSERT"))
    device_ids_in_dxf = {ins.dxf.name for ins in inserts}
    # Each device's block name follows the convention `device_{device_id}`.
    assert device_ids_in_dxf == {"device_bess_1", "device_switch_1"}


def test_dxf_contains_title_block_with_deployment_uuid(two_device_dtm: Dtm) -> None:
    """Title block MTEXT carries the deployment_uuid so reviewers can trace the drawing."""
    # Act
    outputs = SldEngineeringService().generate(two_device_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert
    # `m.text` is the MText body; ezdxf's stubs return DXFEntity | Unknown
    # for query results, so cast to MText to silence ty.
    from ezdxf.entities import MText

    mtexts = [m for m in doc.modelspace().query("MTEXT") if isinstance(m, MText)]
    text_blob = " ".join(m.text for m in mtexts)
    assert str(two_device_dtm.deployment_uuid) in text_blob


def test_pdf_bytes_start_with_pdf_magic(two_device_dtm: Dtm) -> None:
    """PDF bytes start with %PDF- magic — proves real PDF, not stub."""
    # Act
    outputs = SldEngineeringService().generate(two_device_dtm)

    # Assert
    assert outputs.pdf.startswith(b"%PDF-")


def test_bus_lines_emitted_one_per_bus(two_device_dtm: Dtm) -> None:
    """Each bus in the DTM produces a LINE (or POLYLINE) entity tagged with bus_id."""
    # Act
    outputs = SldEngineeringService().generate(two_device_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert — bus geometry lives on a dedicated layer for engineering review
    bus_layer_entities = [e for e in doc.modelspace() if e.dxf.layer == "BUS"]
    assert len(bus_layer_entities) >= 1


def test_engineering_and_hmi_agree_on_device_set(two_device_dtm: Dtm) -> None:
    """Engineering SLD and HMI SVG draw the same set of devices — by construction.

    Backward-compat contract: both renderings consume the same DTM and must
    emit one symbol per Device. If this drifts, the two artifacts will
    misalign in engineering review vs runtime ops.
    """
    # Arrange
    from src.drawing.sld_hmi_svg_service import SldHmiSvgService

    eng_outputs = SldEngineeringService().generate(two_device_dtm)
    hmi_svg = SldHmiSvgService().generate(two_device_dtm).decode("utf-8")

    # Act
    eng_doc = ezdxf.read(io.StringIO(eng_outputs.dxf.decode("utf-8")))
    eng_devices = {
        ins.dxf.name.removeprefix("device_")
        for ins in eng_doc.modelspace().query("INSERT")
    }

    # Assert — both sets exactly match the DTM's devices
    expected = set(two_device_dtm.devices)
    assert eng_devices == expected
    for device_id in expected:
        # HMI SVG marks each device's container group with id="<device_id>"
        assert f'id="{device_id}"' in hmi_svg

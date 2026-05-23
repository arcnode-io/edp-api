"""CommsDiagramService unit tests — paper-grade comms topology DXF + PDF."""

import io

import ezdxf
import pytest

from src.drawing.comms_diagram_service import (
    CommsDiagramOutputs,
    CommsDiagramService,
)
from src.drawing.conftest import make_device, make_dtm
from src.shared.schemas.dtm import Dtm
from src.shared.schemas.measurement import Measurement
from src.shared.schemas.template import DeviceTemplate, TemplateKind
from src.shared.schemas.template_protocols import (
    Dnp3Binding,
    ModbusBinding,
    RedfishBinding,
    SnmpBinding,
)


def _tpl(
    slug: str, binding: ModbusBinding | Dnp3Binding | SnmpBinding | RedfishBinding
) -> DeviceTemplate:
    """Leaf template with one measurement carrying the given binding."""
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
def multi_protocol_dtm() -> Dtm:
    """4 devices, 4 protocols — one per family."""
    return make_dtm(
        devices={
            "switchgear_1": make_device("switchgear_1", template="switchgear"),
            "relay_1": make_device("relay_1", template="protective_relay"),
            "switch_1": make_device("switch_1", template="network_switch"),
            "gpu_1": make_device("gpu_1", template="gpu_node"),
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
            "network_switch": _tpl(
                "network_switch",
                SnmpBinding(protocol="snmp", oid="1.3.6.1.2.1.1.5.0"),
            ),
            "gpu_node": _tpl(
                "gpu_node",
                RedfishBinding(protocol="redfish", uri="/redfish/v1/Systems/1"),
            ),
        },
    )


def test_generate_returns_dxf_and_pdf_bytes(multi_protocol_dtm: Dtm) -> None:
    """generate() returns an outputs bundle with non-empty dxf + pdf bytes."""
    # Act
    actual = CommsDiagramService().generate(multi_protocol_dtm)

    # Assert
    assert isinstance(actual, CommsDiagramOutputs)
    assert len(actual.dxf) > 0
    assert len(actual.pdf) > 0


def test_pdf_starts_with_magic(multi_protocol_dtm: Dtm) -> None:
    """PDF bytes start with %PDF- — proves real vector PDF."""
    # Act
    outputs = CommsDiagramService().generate(multi_protocol_dtm)

    # Assert
    assert outputs.pdf.startswith(b"%PDF-")


def test_dxf_emits_one_device_node_per_dtm_device(multi_protocol_dtm: Dtm) -> None:
    """Each device in the DTM appears as a labelled node block in the diagram."""
    # Act
    outputs = CommsDiagramService().generate(multi_protocol_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert
    inserts = list(doc.modelspace().query("INSERT"))
    device_inserts = [i for i in inserts if i.dxf.name.startswith("device_")]
    device_ids_in_dxf = {i.dxf.name.removeprefix("device_") for i in device_inserts}
    assert device_ids_in_dxf == set(multi_protocol_dtm.devices)


def test_dxf_groups_devices_by_protocol_family(multi_protocol_dtm: Dtm) -> None:
    """Each protocol family present in the DTM gets a labelled cluster header."""
    # Act
    outputs = CommsDiagramService().generate(multi_protocol_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert — cluster header text exists for each protocol
    from ezdxf.entities import MText

    mtexts = [m for m in doc.modelspace().query("MTEXT") if isinstance(m, MText)]
    blob = " ".join(m.text for m in mtexts)
    assert "MODBUS TCP" in blob
    assert "DNP3 TCP" in blob
    assert "SNMP" in blob
    assert "REDFISH" in blob


def test_dxf_carries_title_block_with_deployment_uuid(multi_protocol_dtm: Dtm) -> None:
    """Title block MTEXT carries the deployment_uuid."""
    # Act
    outputs = CommsDiagramService().generate(multi_protocol_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert
    from ezdxf.entities import MText

    mtexts = [m for m in doc.modelspace().query("MTEXT") if isinstance(m, MText)]
    blob = " ".join(m.text for m in mtexts)
    assert str(multi_protocol_dtm.deployment_uuid) in blob
    assert "COMMS" in blob.upper()


def test_dxf_emits_host_port_label_per_device(multi_protocol_dtm: Dtm) -> None:
    """Every device with a Connection gets its host:port surfaced in the diagram."""
    # Act
    outputs = CommsDiagramService().generate(multi_protocol_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert — `10.0.0.1:502` is the default connection from conftest helpers
    text_entities = list(doc.modelspace().query("TEXT"))
    text_blob = " ".join(t.dxf.text for t in text_entities)
    assert "10.0.0.1:502" in text_blob

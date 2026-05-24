"""InstallSequenceService unit tests — PERT-style commissioning DAG (PDF).

Per ARCNODE artifact-pipeline spec: PDF only (project-mgmt artifact,
not engineering drawing — no DXF). Uses graphviz `dot` to render the
layered DAG.
"""

import pytest

from src.drawing.conftest import make_device, make_dtm
from src.drawing.install_sequence_service import (
    InstallSequenceOutputs,
    InstallSequenceService,
)
from src.shared.schemas.dtm import Dtm
from src.shared.schemas.install_task import CxLevel, InstallTask
from src.shared.schemas.measurement import Measurement, Publisher
from src.shared.schemas.template import DeviceTemplate, TemplateKind


def _module_tpl(slug: str) -> DeviceTemplate:
    return DeviceTemplate(
        template=slug,
        kind=TemplateKind.MODULE,
        description=slug,
        measurements={
            "total": Measurement(
                unit="watts", type="float", publisher=Publisher.LINE_CONTROLLER
            )
        },
        install_tasks=[
            InstallTask(
                name="container_set",
                est_minutes=240,
                crew_role="general",
                cx_level=CxLevel.L1,
            ),
        ],
    )


def _pdu_tpl() -> DeviceTemplate:
    from src.shared.schemas.template_protocols import ModbusBinding

    return DeviceTemplate(
        template="pdu",
        kind=TemplateKind.LEAF,
        equipment_id="CMP-PDU-001",
        vendor="Server Tech",
        model="PRO3X",
        description="pdu test fixture",
        measurements={
            "v": Measurement(
                unit="volts",
                type="float",
                binding=ModbusBinding(
                    protocol="modbus_tcp", function_code=4, address=100
                ),
            )
        },
        install_tasks=[
            InstallTask(
                name="mount_in_rack",
                est_minutes=20,
                crew_role="electrician",
                cx_level=CxLevel.L1,
            ),
            InstallTask(
                name="wire_input_feed",
                depends_on=["mount_in_rack"],
                est_minutes=30,
                crew_role="electrician",
                cx_level=CxLevel.L2,
            ),
            InstallTask(
                name="snmp_commission",
                depends_on=["wire_input_feed"],
                est_minutes=15,
                crew_role="it",
                cx_level=CxLevel.L3,
            ),
        ],
    )


@pytest.fixture
def small_dtm() -> Dtm:
    """1 compute module + 2 PDUs as children — minimal DAG fixture."""
    return make_dtm(
        devices={
            "compute_module_1": make_device(
                "compute_module_1", template="compute_module"
            ).model_copy(update={"connection": None, "parent": None}),
            "pdu_a": make_device("pdu_a", template="pdu").model_copy(
                update={"parent": "compute_module_1"}
            ),
            "pdu_b": make_device("pdu_b", template="pdu").model_copy(
                update={"parent": "compute_module_1"}
            ),
        },
        templates={
            "compute_module": _module_tpl("compute_module"),
            "pdu": _pdu_tpl(),
        },
    )


def test_generate_returns_pdf_bytes(small_dtm: Dtm) -> None:
    """generate() returns a PDF byte stream from graphviz."""
    # Act
    actual = InstallSequenceService().generate(small_dtm)

    # Assert
    assert isinstance(actual, InstallSequenceOutputs)
    assert actual.pdf.startswith(b"%PDF-")


def test_dot_source_carries_per_device_task_labels(small_dtm: Dtm) -> None:
    """Each device's tasks appear as nodes in the DOT source.

    PDF streams are FlateDecode-compressed so labels aren't grep-able
    in PDF bytes; verify the DOT layer instead — it's where label
    presence actually originates.
    """
    from src.drawing._install_dag import build_install_dag
    from src.drawing._install_dot import build_dot_source

    # Act
    dag = build_install_dag(small_dtm)
    dot_src = build_dot_source(dag, deployment_uuid=small_dtm.deployment_uuid)

    # Assert
    assert "pdu_a__mount_in_rack" in dot_src
    assert "pdu_b__wire_input_feed" in dot_src


def test_critical_path_is_longest_total_minutes(small_dtm: Dtm) -> None:
    """Critical path = longest cumulative est_minutes — verify against fixture.

    Fixture: compute_module(L1=240) + pdu_a/pdu_b(L1=20, L2=30, L3=15).
    Longest path: container_set (240) -> pdu_x.wire_input_feed (30)
    -> pdu_x.snmp_commission (15) = 285 min. The L1 PDU task itself
    isn't on the path (240 from container dominates the 20).
    """
    from src.drawing._install_dag import build_install_dag

    # Act
    dag = build_install_dag(small_dtm)

    # Assert — container task is the longest L1 contributor; L3 PDU end is the tail.
    assert "compute_module_1__container_set" in dag.critical_path
    # One of the two PDUs is on the critical path through L2 → L3.
    pdu_a_end = "pdu_a__snmp_commission" in dag.critical_path
    pdu_b_end = "pdu_b__snmp_commission" in dag.critical_path
    assert pdu_a_end or pdu_b_end

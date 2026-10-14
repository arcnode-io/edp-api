"""with_summaries: real per-artifact counts for the delivery portal."""

from datetime import UTC, datetime
from uuid import UUID

from src.bom_generator.bom_test_support import ORDER
from src.bom_generator.bom_models import BomSection
from src.bom_generator.bom_models import Bom, BomLineItem, ProcurementPath
from src.cable_hose_schedule.cable_hose_schedule_models import (
    CableEntry,
    CableHoseSchedule,
    HoseEntry,
)
from src.pipeline.artifact_summary import with_summaries
from src.shared.schemas.artifact import ArtifactKind, ArtifactRef, ArtifactSummary
from src.shared.schemas.dtm import Bus, BusMember, Device, Dtm

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000123")


def _line(part_number: str, vendor: str, qty: int) -> BomLineItem:
    return BomLineItem(
        section=BomSection.COMPUTE,
        ref_des="C1",
        part_number=part_number,
        vendor=vendor,
        description=part_number,
        qty=qty,
        procurement_path=ProcurementPath.CATALOG,
    )


def _cable(tag: str, cable_type: str) -> CableEntry:
    return CableEntry(
        tag=tag,
        service="Comms - Modbus TCP",
        from_device="pdu_1",
        from_port="TCP/502",
        to_device="network_switch_1",
        to_port="eth1",
        cable_type=cable_type,
    )


def _hose(tag: str) -> HoseEntry:
    return HoseEntry(
        tag=tag,
        service="Coolant Supply",
        from_device="cdu_1",
        from_port="supply",
        to_device="gpu_node_1",
        to_port="inlet",
        hose_type="EPDM 1in PG/W rated",
    )


def _ref(kind: ArtifactKind, fmt: str, plate_id: str | None = None) -> ArtifactRef:
    return ArtifactRef(
        kind=kind, format=fmt, url=f"s3://x/{kind}.{fmt}", plate_id=plate_id
    )


def test_every_counted_artifact_carries_its_real_counts() -> None:
    # Arrange
    bom = Bom(
        deployment_id=DEPLOYMENT_ID,
        profile="commercial_ac",
        manifest_version="0.0.0-test",
        generated_at=datetime.now(UTC),
        compute_container_qty=2,
        grid_container_qty=1,
        order=ORDER,
        line_items=[
            _line("SYS-421GE", "Supermicro", 8),
            _line("AP8886", "APC", 6),
            _line("AP8887", "APC", 2),
            _line("ARC-PLT-CG-001", "ARCNODE (custom fab)", 3),
            _line("ARC-PLT-CD-001", "ARCNODE (custom fab)", 2),
        ],
    )
    cable_hose = CableHoseSchedule(
        deployment_uuid=DEPLOYMENT_ID,
        generated_at=datetime.now(UTC),
        cables=[_cable("CBL-0001", "Cat6 STP"), _cable("CBL-0002", "Cat6 STP")],
        hoses=[_hose("HOS-0001")],
    )
    # Reason: model_construct skips template/sizing wiring we don't count.
    dtm = Dtm.model_construct(
        devices={
            d: Device(device_id=d, template="t")
            for d in ("switchgear_1", "poi_meter_1", "pdu_1")
        },
        buses=[
            Bus(
                bus_id="ac_main_1",
                type="ac",
                members=[BusMember(device_id="switchgear_1")],
            )
        ],
    )
    urls = [
        _ref(ArtifactKind.BOM, "json"),
        _ref(ArtifactKind.BOM, "xlsx"),
        _ref(ArtifactKind.CABLE_HOSE_SCHEDULE, "json"),
        _ref(ArtifactKind.DTM, "json"),
        _ref(ArtifactKind.INTERFACE_PLATE, "step", plate_id="CG"),
        _ref(ArtifactKind.INTERFACE_PLATE, "dxf", plate_id="CD"),
        _ref(ArtifactKind.SLD, "pdf"),
    ]

    # Act
    actual = [
        (r.kind, r.format, r.summary)
        for r in with_summaries(
            urls,
            bom=bom,
            dtm=dtm,
            cable_hose=cable_hose,
            deployment_context="commercial",
        )
    ]

    # Assert
    bom_summary = ArtifactSummary(line_items=5, vendors=3)
    expected = [
        (ArtifactKind.BOM, "json", bom_summary),
        (ArtifactKind.BOM, "xlsx", bom_summary),
        (
            ArtifactKind.CABLE_HOSE_SCHEDULE,
            "json",
            ArtifactSummary(runs=3, media_kinds=2),
        ),
        (ArtifactKind.DTM, "json", ArtifactSummary(devices=3, buses=1)),
        (ArtifactKind.INTERFACE_PLATE, "step", ArtifactSummary(plates=3)),
        (ArtifactKind.INTERFACE_PLATE, "dxf", ArtifactSummary(plates=2)),
        (ArtifactKind.SLD, "pdf", None),
    ]
    assert actual == expected

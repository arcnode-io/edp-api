"""The panel builder learns the partial container's breakers are fewer."""

from src.bom_generator.bom_container_groups import with_partial_panel_note
from src.bom_generator.bom_models import BomLineItem, BomSection, ProcurementPath


def test_partial_container_panelboard_gets_breakers_for_its_pdus_only() -> None:
    # Arrange — 8 servers: C2 holds 1, so 1 PDU per side
    panel = BomLineItem(
        section=BomSection.COMPUTE,
        ref_des="C1-C2: PNL-1",
        part_number="QO panelboard",
        vendor="Square D",
        description="panelboard",
        qty=2,
        procurement_path=ProcurementPath.ENGINEERED_TO_ORDER,
        equipment_id="CMP-PNL-001",
    )

    # Act
    actual = with_partial_panel_note([panel], nodes=8, compute_qty=2)[0].notes

    # Assert
    assert actual == (
        "C2 holds 1 server: branch breakers for its 2 PDUs, CDU and dry cooler "
        "only; keep every PDU space so servers can be added."
    )

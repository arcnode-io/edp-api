"""Site-and-interfaces BOM lines: equipment outside the containers.

Everything the SLD, comms and P&ID draw outside a container appears here,
so the BOM covers what the drawings show: the customer's battery at the
ordered size, the by-others MV and cooling gear it connects through, and
(dc_ext) the outdoor enclosure for the PCS pair on the battery pad.
"""

from src.bom_generator.bom_models import (
    BomLineItem,
    BomOrder,
    BomSection,
    ProcurementPath,
)
from src.bom_generator.bom_ref_des import containers

_COUPLING: dict[str, str] = {
    "ac_coupled": "AC-coupled, ties in at 13.8 kV through customer gear (ADR-016)",
    "dc_integrated_pcs": "DC with its own PCS, ties in at 13.8 kV through customer gear (ADR-016)",
    "dc_external_pcs": "DC strings to the ARCNODE PCS pair on the battery pad (ADR-022)",
}


def _line(
    ref: str,
    part: str,
    vendor: str,
    description: str,
    qty: int,
    path: ProcurementPath,
    notes: str,
) -> BomLineItem:
    return BomLineItem(
        section=BomSection.SITE,
        ref_des=ref,
        part_number=part,
        vendor=vendor,
        description=description,
        qty=qty,
        procurement_path=path,
        notes=notes,
    )


def site_lines(order: BomOrder, compute_qty: int, grid_qty: int) -> list[BomLineItem]:
    """Site equipment for this order, ARCNODE-supplied or not."""
    by_others = ProcurementPath.BY_OTHERS
    dc_ext = order.bess_coupling == "dc_external_pcs"
    lines = [
        _line(
            "BESS-1",
            "Customer-selected",
            "Customer",
            f"Battery energy storage system, {order.bess_capacity_mwh:g} MWh, "
            f"{_COUPLING[order.bess_coupling]}",
            1,
            ProcurementPath.CUSTOMER_SUPPLIED,
            "Customer brings the battery (ADR-001); the EMS supervises it.",
        ),
        _line(
            "SITE-MV",
            "Site MV distribution",
            "By others",
            "13.8 kV site bus joining the utility service, grid containers and BESS",
            1,
            by_others,
            "Site MV contractor (ADR-018).",
        ),
        _line(
            "POI-CT/PT",
            "Revenue-class CTs and PTs",
            "By others",
            "Instrument transformers for the POI meter at the utility service",
            1,
            by_others,
            "Install with GRD-MTR-001, which ships loose with G1 (ADR-020).",
        ),
        _line(
            "EMS-GW",
            "platform-ems-iso host",
            "By others",
            "EMS gateway host running the ARCNODE EMS image",
            1,
            by_others,
            "Uplinks to G1's management switch (ADR-019).",
        ),
        _line(
            f"{containers('C', 1, compute_qty)}: PUMP-1",
            "Facility coolant pump",
            "By others",
            "Primary-loop circulation pump, one per compute container",
            compute_qty,
            by_others,
            "Facility loop per P&ID sheet 2.",
        ),
        _line(
            f"{containers('C', 1, compute_qty)}: TANK-1",
            "Buffer tank",
            "By others",
            "Primary-loop buffer tank, one per compute container",
            compute_qty,
            by_others,
            "Facility loop per P&ID sheet 2.",
        ),
    ]
    if dc_ext:
        lines.append(
            _line(
                f"{containers('G', 1, grid_qty)}: PCS-ENC-1",
                "To spec ADR-022 (PCS enclosure)",
                "EPC Power (RFQ)",
                "Outdoor enclosure with liquid cooling for the 2x PD500 PCS pair",
                grid_qty,
                ProcurementPath.ENGINEERED_TO_ORDER,
                "PCS pair sits on the battery pad (ADR-022); EPC spec via sales.",
            )
        )
    else:
        lines += [
            _line(
                "T-BESS",
                "BESS step-up transformer",
                "By others",
                "Step-up transformer, BESS AC to 13.8 kV",
                1,
                by_others,
                "BESS interconnection by others (ADR-016).",
            ),
            _line(
                "Q-BESS",
                "MV disconnect",
                "By others",
                "13.8 kV disconnect for the BESS tie-in",
                1,
                by_others,
                "BESS interconnection by others (ADR-016).",
            ),
        ]
    return lines

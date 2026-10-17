"""Spec / plate spec yaml → BOM line items."""

from src.bom_generator.bom_models import BomLineItem, BomSection, ProcurementPath


def spec_to_catalog_line(
    spec: dict, qty: int, section: BomSection, ref_des: str, notes: str = ""
) -> BomLineItem:
    """Map spec.yaml fields → BOM line item.

    A spec whose vendor is still TBD is a requirement spec: the part is
    bought engineered to order, by RFQ against that spec. A spec can also
    name a reference design (vendor + model) and still declare
    `procurement_path: engineered_to_order`; the line then carries that
    reference design.
    """
    open_vendor = spec.get("vendor") == "TBD"
    eto = open_vendor or spec.get("procurement_path") == "engineered_to_order"
    return BomLineItem(
        section=section,
        ref_des=ref_des,
        part_number=(
            f"To spec {spec['equipment_id']}" if open_vendor else spec["model_number"]
        ),
        vendor="RFQ" if open_vendor else spec["vendor"],
        description=spec.get("description", ""),
        qty=qty,
        procurement_path=(
            ProcurementPath.ENGINEERED_TO_ORDER if eto else ProcurementPath.CATALOG
        ),
        notes=notes or _eto_note(spec, open_vendor, eto),
        equipment_id=spec["equipment_id"],
        datasheet_url=spec.get("datasheet_url"),
        lead_time_weeks=spec.get("lead_time_weeks"),
        fab_tier=spec.get("fab_tier"),
        # Track-A enrichment — install_video_url is a new spec field;
        # NDAA + TAA are DERIVED from existing schema (restricted_entities
        # + fab_tier) to avoid duplicate-source drift.
        install_video_url=spec.get("install_video_url"),
        ndaa_compliant=_derive_ndaa(spec),
        taa_compliant=_derive_taa(spec),
    )


def _derive_ndaa(spec: dict) -> bool:
    """True iff spec.restricted_entities does NOT include `NDAA_889`.

    A spec without restricted_entities (or with an empty list) is by
    convention NDAA-compliant — that's the "checked clean" state per
    the equipment_spec_schema.md doc.
    """
    restricted = spec.get("restricted_entities") or []
    return "NDAA_889" not in restricted


def _derive_taa(spec: dict) -> bool:
    """True iff spec.fab_tier is federal_civilian or dod_eligible.

    Federal procurement (FAR Part 25) requires TAA compliance, so
    classifying equipment as federally procurable implies TAA
    compliance. `commercial` fab_tier doesn't claim either way →
    False (= unverified).
    """
    return spec.get("fab_tier") in {"federal_civilian", "dod_eligible"}


def plate_part_number(plate_id: str, deployment_context: str) -> str:
    """ARCNODE PN for a plate; defense builds get the -D suffix."""
    revision = "001"  # v1 — pull from plate_spec when versioning lands
    pn = f"ARC-PLT-{plate_id}-{revision}"
    if deployment_context != "commercial":
        pn += "-D"
    return pn


def plate_spec_to_custom_line(
    plate_id: str,
    plate_spec: dict,
    plate_step_url: str,
    qty: int,
    section: BomSection,
    ref_des: str,
    deployment_context: str = "commercial",
) -> BomLineItem:
    """Map plate spec.yaml + URL → custom_fabrication BOM line item."""
    pn = plate_part_number(plate_id, deployment_context)
    ctx = plate_spec.get("deployment_contexts", {}).get(deployment_context, {})
    return BomLineItem(
        section=section,
        ref_des=ref_des,
        part_number=pn,
        vendor="CNC shop, to ARCNODE drawing",
        description=plate_spec.get("description", f"Interface Plate, {plate_id}"),
        qty=qty,
        procurement_path=ProcurementPath.CUSTOM_FABRICATION,
        material=ctx.get("material"),
        finish=ctx.get("finish"),
        drawing_ref=f"{pn}.dxf",
        drawing_url=plate_step_url.replace(".step", ".dxf"),
    )


def shell_to_custom_line(
    shell: dict, qty: int, section: BomSection, ref_des: str
) -> BomLineItem:
    """Container shell (bom.yaml `shell:` block) → custom_fabrication line.

    A stock 10ft ISO container; a fab shop cuts it to the ARCNODE drawings.
    """
    return BomLineItem(
        section=section,
        ref_des=ref_des,
        part_number=shell["part_number"],
        vendor="Container supplier",
        description=shell["description"],
        qty=qty,
        procurement_path=ProcurementPath.CUSTOM_FABRICATION,
    )


def _eto_note(spec: dict, open_vendor: bool, eto: bool) -> str:
    if open_vendor:
        return "Requirement spec; vendor by RFQ."
    if eto:
        return f"Reference design; bought by RFQ against spec {spec['equipment_id']}."
    return ""

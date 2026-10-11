"""Spec / plate spec yaml → BOM line items."""

from src.bom_generator.bom_models import BomLineItem, ProcurementPath


def spec_to_catalog_line(spec: dict, qty: int) -> BomLineItem:
    """Map spec.yaml fields → catalog BOM line item."""
    return BomLineItem(
        part_number=spec.get("model_number", spec["equipment_id"]),
        vendor=spec.get("vendor", "TBD"),
        description=spec.get("description", ""),
        qty=qty,
        procurement_path=ProcurementPath.CATALOG,
        datasheet_url=spec.get("datasheet_url"),
        lead_time_weeks=spec.get("lead_time_weeks"),
        unit_cost_usd=spec.get("unit_cost_usd"),
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


def plate_spec_to_custom_line(
    plate_id: str,
    plate_spec: dict,
    plate_step_url: str,
    qty: int,
    deployment_context: str = "commercial",
) -> BomLineItem:
    """Map plate spec.yaml + URL → custom_fabrication BOM line item."""
    revision = "001"  # v1 — pull from plate_spec when versioning lands
    pn = f"ARC-PLT-{plate_id}-{revision}"
    if deployment_context != "commercial":
        pn += "-D"

    ctx = plate_spec.get("deployment_contexts", {}).get(deployment_context, {})
    return BomLineItem(
        part_number=pn,
        vendor="ARCNODE (custom fab)",
        description=plate_spec.get("description", f"Interface Plate, {plate_id}"),
        qty=qty,
        procurement_path=ProcurementPath.CUSTOM_FABRICATION,
        material=ctx.get("material"),
        finish=ctx.get("finish"),
        drawing_ref=f"{pn}.dxf",
        drawing_url=plate_step_url.replace(".step", ".dxf"),
    )


def shell_to_custom_line(shell: dict, qty: int) -> BomLineItem:
    """Container shell (bom.yaml `shell:` block) → custom_fabrication line."""
    return BomLineItem(
        part_number=shell["part_number"],
        vendor="ARCNODE (custom fab)",
        description=shell["description"],
        qty=qty,
        procurement_path=ProcurementPath.CUSTOM_FABRICATION,
    )

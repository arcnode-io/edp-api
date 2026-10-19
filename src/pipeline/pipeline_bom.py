"""The BOM's inputs from the order, and live distributor offers merged in.

Split out of pipeline_service.py (200-line budget).
"""

from src.bom_enrichment.enrichment_models import DistributorOffer
from src.bom_enrichment.enrichment_service import EnrichmentService
from src.bom_generator.bom_models import Bom, BomOrder
from src.bom_generator.bom_pricing import live_price, order_budget
from src.shared.enums import DeploymentContext
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.module_resolution import ModuleResolution


def attach_offers(bom: Bom, enrichment: EnrichmentService) -> None:
    """Fetch per-MPN offers across all configured distributors, merge into BOM.

    Looks up by `BomLineItem.part_number` (which IS the MPN for catalog
    items per `spec_lines.spec_to_catalog_line`). Custom-fab
    lines (plates, shells) are skipped — no external distributor offer
    exists. Each line's `offers` field gets the full list of returned
    offers (including error-offers, so a reviewer sees which distributors
    failed for this MPN).
    """
    catalog_mpns = sorted(
        {
            li.part_number
            for li in bom.line_items
            if li.procurement_path.value == "catalog"
        }
    )
    if not catalog_mpns:
        return
    enriched = enrichment.enrich(catalog_mpns)
    for line in bom.line_items:
        result = enriched.get(line.part_number)
        if result is None:
            continue
        line.offers = result.offers
        cheapest = _cheapest_priced_offer(result.offers)
        if cheapest is not None:
            line.price_change_pct_7d = enrichment.price_delta_pct_7d(cheapest)
    # Live distributor prices beat the price list, so the budget moves too
    bom.line_items = [live_price(li) for li in bom.line_items]
    bom.budget = order_budget(bom.line_items)


def _cheapest_priced_offer(offers: list[DistributorOffer]) -> DistributorOffer | None:
    """Lowest-priced non-error offer; None when there's nothing to compare."""
    priced = [o for o in offers if o.error is None and o.unit_cost_usd is not None]
    if not priced:
        return None
    return min(priced, key=lambda o: o.unit_cost_usd or 0)


def bom_order(payload: ConfiguratorPayload, resolution: ModuleResolution) -> BomOrder:
    """The order as placed (payload) and as delivered (resolution)."""
    return BomOrder(
        customer=payload.operator_org,
        site=payload.deployment_site_name,
        deployment_context=payload.deployment_context.value,
        gpu_variant=payload.gpu_variant.value,
        gpus_requested=payload.target_gpu_count,
        gpus_delivered=resolution.gpu_count,
        bess_capacity_mwh=payload.bess_capacity_mwh,
        bess_coupling=payload.bess_coupling.value,
        pcs_qty=resolution.pcs_count,
    )


def context_string(ctx: DeploymentContext) -> str:
    """Map the deployment_context enum to the BOM generator's string param.

    BomGeneratorService accepts "commercial" or "defense_forward" (drives plate
    variant material/finish). SOVEREIGN_GOVERNMENT collapses to defense for the
    BOM since they share hardware (per the manifest profile alignment).
    """
    if ctx == DeploymentContext.COMMERCIAL:
        return "commercial"
    return "defense_forward"

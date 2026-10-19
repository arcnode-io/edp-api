"""Live distributor offers merge onto the BOM's catalog lines."""

from datetime import UTC

from src.bom_generator.bom_test_support import ORDER
from src.bom_generator.bom_models import BomSection
from src.pipeline.pipeline_test_support import (
    DEPLOYMENT_ID,
)


def test_attach_offers_merges_distributor_offers_onto_catalog_lines() -> None:
    """`attach_offers` populates each catalog line's `offers` from enrichment.

    Direct unit-level test of the merge helper — the higher-level
    pipeline tests use an empty bom.yaml fixture so wouldn't exercise
    the catalog-line path. This test gives `attach_offers` a real Bom
    with one catalog + one custom-fab line and asserts only the catalog
    line gets offers (custom-fab plates have no distributor).
    """
    # Arrange
    from datetime import datetime as _dt

    from src.bom_enrichment._base_scraper import DistributorClient
    from src.bom_enrichment.enrichment_models import (
        DistributorId,
        DistributorOffer,
    )
    from src.bom_enrichment.enrichment_service import EnrichmentService
    from src.bom_generator.bom_models import Bom, BomLineItem, ProcurementPath
    from src.pipeline.pipeline_bom import attach_offers

    class _MockClient(DistributorClient):
        @property
        def distributor_id(self) -> DistributorId:
            return "graybar"

        def fetch_offer(self, mpn: str) -> DistributorOffer:
            return DistributorOffer(
                distributor="graybar",
                mpn=mpn,
                stock_count=5,
                unit_cost_usd=99.99,
                refreshed_at=_dt.now(UTC),
            )

        def close(self) -> None:
            pass

    bom = Bom(
        deployment_id=DEPLOYMENT_ID,
        profile="commercial_ac",
        manifest_version="0.0.0-test",
        generated_at=_dt.now(UTC),
        compute_container_qty=1,
        grid_container_qty=0,
        order=ORDER,
        line_items=[
            BomLineItem(
                section=BomSection.COMPUTE,
                ref_des="C1",
                part_number="MPN-CATALOG-1",
                vendor="Acme",
                description="x",
                qty=1,
                procurement_path=ProcurementPath.CATALOG,
            ),
            BomLineItem(
                section=BomSection.COMPUTE,
                ref_des="C1",
                part_number="ARC-PLT-CG-001",
                vendor="ARCNODE (custom fab)",
                description="plate",
                qty=1,
                procurement_path=ProcurementPath.CUSTOM_FABRICATION,
            ),
        ],
    )

    # Act
    attach_offers(bom, EnrichmentService([_MockClient()]))

    # Assert — catalog line got an offer; custom-fab line did NOT
    catalog_line = next(
        li for li in bom.line_items if li.procurement_path == ProcurementPath.CATALOG
    )
    plate_line = next(
        li
        for li in bom.line_items
        if li.procurement_path == ProcurementPath.CUSTOM_FABRICATION
    )
    assert len(catalog_line.offers) == 1
    assert catalog_line.offers[0].unit_cost_usd == 99.99
    assert catalog_line.offers[0].distributor == "graybar"
    assert plate_line.offers == []
    # the live price lands on the line and in the order budget
    assert (catalog_line.unit_cost_usd, bom.budget and bom.budget.total_usd) == (
        99.99,
        99.99,
    )

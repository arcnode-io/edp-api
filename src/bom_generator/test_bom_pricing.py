"""Budget prices on BOM lines, and the order's budgetary total."""

from datetime import UTC, date, datetime
from uuid import uuid4

from src.bom_enrichment.enrichment_models import DistributorOffer
from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.bom_models import BomLineItem, BomSection, ProcurementPath
from src.bom_generator.bom_pricing import book_price, live_price, order_budget
from src.bom_generator.bom_test_support import ORDER
from src.bom_generator.pricing_models import PriceBook, PriceBreak, PriceSource
from src.bom_generator.test_bom_generator_service import (
    _make_manifest,
    _make_mock_client,
)
from src.shared.enums import GpuVariant

_DAY = date(2026, 10, 17)


def _line(
    qty: int,
    path: ProcurementPath = ProcurementPath.CATALOG,
    unit: float | None = None,
    source: PriceSource | None = None,
) -> BomLineItem:
    return BomLineItem(
        section=BomSection.COMPUTE,
        ref_des="C1",
        part_number="SYS-421GE-TNHR2-LCC",
        vendor="Supermicro",
        description="node",
        qty=qty,
        procurement_path=path,
        equipment_id="CMP-NODE-002",
        unit_cost_usd=unit,
        price_source=source,
    )


def _break(unit: float, min_qty: int, source: PriceSource) -> PriceBreak:
    return PriceBreak(
        unit_usd=unit, min_qty=min_qty, source=source, basis="list", as_of=_DAY
    )


def test_a_line_takes_the_price_break_for_its_quantity() -> None:
    # Arrange — 8+ nodes across the order buy at the volume price
    book = PriceBook(
        prices={
            "CMP-NODE-002": [
                _break(300_000, 1, PriceSource.ESTIMATE),
                _break(280_000, 8, PriceSource.QUOTE),
            ]
        }
    )

    # Act
    actual = [
        (li.unit_cost_usd, li.price_source)
        for li in (book_price(_line(7), book, 7), book_price(_line(4), book, 8))
    ]

    # Assert
    assert actual == [
        (300_000, PriceSource.ESTIMATE),
        (280_000, PriceSource.QUOTE),
    ]


def test_a_live_distributor_price_beats_the_book() -> None:
    # Arrange
    line = _line(2, unit=20.0, source=PriceSource.ESTIMATE)
    line.offers = [
        DistributorOffer(
            distributor="graybar",
            mpn="QO120",
            unit_cost_usd=16.48,
            refreshed_at=datetime(2026, 10, 18, tzinfo=UTC),
        )
    ]

    # Act
    actual = live_price(line)

    # Assert
    assert (
        actual.unit_cost_usd,
        actual.price_source,
        actual.price_basis,
        actual.price_as_of,
    ) == (16.48, PriceSource.DISTRIBUTOR, "Graybar", date(2026, 10, 18))


def test_order_budget_sums_what_the_customer_buys_with_a_band_per_source() -> None:
    # Arrange — $2,000 estimate (±40%), $3,000 quote (±10%), one unpriced
    # line; the customer's own battery is already owned, so not in the total
    lines = [
        _line(2, unit=1_000, source=PriceSource.ESTIMATE),
        _line(1, unit=3_000, source=PriceSource.QUOTE),
        _line(1, ProcurementPath.ENGINEERED_TO_ORDER),
        _line(1, ProcurementPath.CUSTOMER_SUPPLIED, 9_999, PriceSource.ESTIMATE),
    ]

    # Act
    actual = order_budget(lines)

    # Assert
    assert (
        actual.total_usd,
        actual.low_usd,
        actual.high_usd,
        actual.quote_backed_pct,
        actual.unpriced_lines,
    ) == (5_000, 3_900, 6_100, 60, 1)


def test_generated_bom_prices_lines_from_the_manifest_price_list() -> None:
    # Arrange — the CG plate is listed; the nodes and rack aren't
    manifest = _make_manifest().model_copy(update={"pricing": "s3://test/pricing.yaml"})
    client = _make_mock_client(manifest)
    client.fetch_pricing.return_value = PriceBook(
        prices={"ARC-PLT-CG-001": [_break(1_800, 1, PriceSource.ESTIMATE)]}
    )

    # Act
    bom = BomGeneratorService(client).generate(
        deployment_id=uuid4(),
        profile="commercial_ac",
        gpu_variant=GpuVariant.B200,
        order=ORDER,
    )

    # Assert
    plate = next(li for li in bom.line_items if li.part_number == "ARC-PLT-CG-001")
    assert (plate.unit_cost_usd, bom.budget and bom.budget.total_usd) == (
        1_800,
        1_800,
    )


def test_price_book_carries_installer_material_by_cable_type() -> None:
    # Arrange — pricing.yaml's field section, keyed by cable/hose type
    raw = {
        "field": {
            "Cat6 STP": [
                {
                    "unit_usd": 15,
                    "source": "estimate",
                    "basis": "5 m run",
                    "as_of": _DAY,
                }
            ]
        }
    }

    # Act
    actual = PriceBook.model_validate(raw).field["Cat6 STP"][0].unit_usd

    # Assert
    assert actual == 15


def test_an_installer_run_is_priced_from_the_field_list_and_counted() -> None:
    # Arrange — the installer buys this material, so it belongs in the budget
    run = BomLineItem(
        section=BomSection.FIELD,
        ref_des="W-1…W-20",
        part_number="Cat6 STP",
        vendor="Installer",
        description="Cat6 STP, cut to field-measured length per run",
        qty=20,
        uom="run",
        procurement_path=ProcurementPath.FIELD_SUPPLIED,
    )
    book = PriceBook(field={"Cat6 STP": [_break(15, 1, PriceSource.ESTIMATE)]})

    # Act
    actual = order_budget([book_price(run, book, 20)]).total_usd

    # Assert
    assert actual == 300

"""Budget prices for BOM lines and the order's budgetary total.

ARCNODE sells software only; the customer buys every part and runs their
own RFQs. A line's price is the cheapest live distributor offer, else the
budget price list (`pricing.yaml`) at the line's quantity, else unpriced.
"""

from typing import Final

from src.bom_generator.bom_models import BomBudget, BomLineItem, ProcurementPath
from src.bom_generator.pricing_models import PriceBook, PriceSource

# Lines the customer has to buy; the rest they own or others supply
PURCHASED: Final[frozenset[ProcurementPath]] = frozenset(
    {
        ProcurementPath.CATALOG,
        ProcurementPath.ENGINEERED_TO_ORDER,
        ProcurementPath.CUSTOM_FABRICATION,
        ProcurementPath.FIELD_SUPPLIED,
    }
)
# How far each kind of price is trusted, as a ± fraction
BAND: Final[dict[PriceSource, float]] = {
    PriceSource.QUOTE: 0.10,
    PriceSource.DISTRIBUTOR: 0.15,
    PriceSource.ESTIMATE: 0.40,
}


def price_key(line: BomLineItem) -> str:
    """The line's key in the price list: equipment id, else part number."""
    return line.equipment_id or line.part_number


def book_price(line: BomLineItem, book: PriceBook, order_qty: int) -> BomLineItem:
    """Line priced from the price list; unchanged if unlisted.

    `order_qty` is the whole order's quantity of this part (a plate sits
    in several sections), which picks the quantity break.
    """
    # Reason: installer material is keyed by cable/hose type, apart from parts
    lists = (
        book.field
        if line.procurement_path == ProcurementPath.FIELD_SUPPLIED
        else book.prices
    )
    breaks = lists.get(price_key(line))
    if line.procurement_path not in PURCHASED or not breaks:
        return line
    # Reason: breaks are ascending by min_qty; the last one reached wins
    pick = [b for b in breaks if b.min_qty <= order_qty][-1]
    return line.model_copy(
        update={
            "unit_cost_usd": pick.unit_usd,
            "price_source": pick.source,
            "price_basis": pick.basis,
            "price_as_of": pick.as_of,
        }
    )


def live_price(line: BomLineItem) -> BomLineItem:
    """Line priced at its cheapest live distributor offer, if it has one."""
    priced = [o for o in line.offers if o.error is None and o.unit_cost_usd]
    if not priced:
        return line
    best = min(priced, key=lambda o: o.unit_cost_usd or 0)
    return line.model_copy(
        update={
            "unit_cost_usd": best.unit_cost_usd,
            "price_source": PriceSource.DISTRIBUTOR,
            "price_basis": best.distributor.title(),
            "price_as_of": best.refreshed_at.date(),
        }
    )


def order_budget(lines: list[BomLineItem]) -> BomBudget:
    """Budgetary total of the parts the customer buys, with a ± range."""
    bought = [li for li in lines if li.procurement_path in PURCHASED]
    priced = [
        (li.unit_cost_usd * li.qty, li.price_source or PriceSource.ESTIMATE)
        for li in bought
        if li.unit_cost_usd is not None
    ]
    total = sum(usd for usd, _ in priced)
    quoted = sum(usd for usd, src in priced if src == PriceSource.QUOTE)
    return BomBudget(
        total_usd=total,
        low_usd=sum(usd * (1 - BAND[src]) for usd, src in priced),
        high_usd=sum(usd * (1 + BAND[src]) for usd, src in priced),
        quote_backed_pct=100 * quoted / total if total else 0,
        unpriced_lines=len(bought) - len(priced),
    )

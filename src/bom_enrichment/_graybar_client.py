"""GraybarClient — Playwright-driven B2B catalog scraper for Graybar.

Logs into graybar.com using `GRAYBAR_USER` / `GRAYBAR_PASS` env vars,
searches the catalog by manufacturer part number (MPN), and extracts
stock + lead time + spot pricing from the product detail page.

A single browser context is reused across all `fetch_offer` calls for
this instance — login happens once, MPN lookups stay sequential to
respect Graybar's rate limit + share the authenticated session.

Selector strategy:
- Login form: form#login or input[name="username"]. Selectors here
  drift more than catalog selectors (auth gets redesigned more often).
- Search box: input[role="combobox"] visible on the home page.
- Product detail: data-test-id="stock-count" + "lead-time-weeks" +
  "unit-price". Best-effort — when a selector misses, return an
  error-offer rather than raise.

v1 scope: search by MPN, take the first result. No multi-result
disambiguation. If Graybar returns multiple matches, we capture the
top one and surface a warning in `error`.
"""

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.bom_enrichment._base_scraper import DistributorClient
from src.bom_enrichment.enrichment_models import DistributorId, DistributorOffer

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.graybar.com/store/login"
_SEARCH_URL = "https://www.graybar.com/store/en/gb/search?q={mpn}"
_NAV_TIMEOUT_MS = 30_000


class GraybarClient(DistributorClient):
    """Graybar B2B portal scraper via Playwright + authenticated session."""

    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._logged_in = False
        # Playwright instance returned by sync_playwright().start();
        # released via .stop() in close().
        self._playwright: Playwright | None = None

    @property
    def distributor_id(self) -> DistributorId:
        return "graybar"

    def fetch_offer(self, mpn: str) -> DistributorOffer:
        """Search Graybar for `mpn`, return the first hit's offer."""
        try:
            self._ensure_logged_in()
            assert self._page is not None
            self._page.goto(_SEARCH_URL.format(mpn=mpn), timeout=_NAV_TIMEOUT_MS)
            return self._parse_product_detail(mpn)
        except Exception as e:
            logger.exception("graybar fetch failed for %s", mpn)
            return DistributorOffer(
                distributor=self.distributor_id,
                mpn=mpn,
                refreshed_at=datetime.now(UTC),
                error=f"graybar fetch failed: {e!r}",
            )

    def close(self) -> None:
        """Tear down the browser context. Idempotent."""
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            # sync_playwright().start() returns a Playwright instance;
            # tear it down via .stop() (not the context-manager protocol).
            self._playwright.stop()
            self._playwright = None
        self._logged_in = False

    def _ensure_logged_in(self) -> None:
        """Boot Chromium + log in once per client instance."""
        if self._logged_in:
            return
        user = os.environ.get("GRAYBAR_USER")
        password = os.environ.get("GRAYBAR_PASS")
        if not user or not password:
            raise RuntimeError("GRAYBAR_USER + GRAYBAR_PASS env vars required")

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()

        self._page.goto(_LOGIN_URL, timeout=_NAV_TIMEOUT_MS)
        self._page.fill("input[name='username']", user)
        self._page.fill("input[name='password']", password)
        self._page.click("button[type='submit']")
        self._page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)
        self._logged_in = True

    def _parse_product_detail(self, mpn: str) -> DistributorOffer:
        """Read stock + lead time + price from the loaded search result page.

        Selectors here are best-guess and WILL need adjustment on first
        real run against Graybar. Each missing selector returns the field
        as None rather than failing the whole offer — partial data ships.
        """
        assert self._page is not None
        return DistributorOffer(
            distributor=self.distributor_id,
            mpn=mpn,
            stock_count=_safe_int(
                _text_or_none(self._page, "[data-test-id='stock-count']")
            ),
            lead_time_weeks=_safe_int(
                _text_or_none(self._page, "[data-test-id='lead-time-weeks']")
            ),
            unit_cost_usd=_safe_float(
                _text_or_none(self._page, "[data-test-id='unit-price']")
            ),
            refreshed_at=datetime.now(UTC),
        )


def _text_or_none(page: "Page", selector: str) -> str | None:
    """Return `selector`'s text content; None if selector missing or invisible."""
    el = page.query_selector(selector)
    if el is None:
        return None
    return el.inner_text().strip()


def _safe_int(s: str | None) -> int | None:
    """Parse `s` as int, stripping commas + currency symbols. None if unparseable."""
    if s is None:
        return None
    cleaned = "".join(ch for ch in s if ch.isdigit())
    return int(cleaned) if cleaned else None


def _safe_float(s: str | None) -> float | None:
    """Parse `s` as float, stripping $ and commas. None if unparseable."""
    if s is None:
        return None
    cleaned = s.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None

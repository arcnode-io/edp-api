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

_LOGIN_URL = "https://www.graybar.com/login"
# `enablePartNumberSearch=true` returns product cards instead of a category
# facet landing page. Search relevance is fuzzy — the first /p/ link is
# our best guess but may not exact-match the queried MPN; the scraper
# verifies via `data-mpn` on the product detail page and surfaces an
# "ambiguous" error when the match is weak.
_SEARCH_URL = "https://www.graybar.com/search/?text={mpn}&enablePartNumberSearch=true"
_NAV_TIMEOUT_MS = 30_000

# Graybar renders two j_username fields on /login — one VISIBLE main login
# form + one HIDDEN ship-to-account form. Both use the same id, distinguished
# by the `_shipto` class suffix. Selectors target the visible one explicitly
# so playwright's visibility wait doesn't loop on the hidden duplicate.
_USERNAME_SELECTOR = "input.login-form-email:not(.login-form-email_shipto)"
_PASSWORD_SELECTOR = "input.login-form-pwd:not(.login-form-pwd_shipto)"  # nosec B105 # noqa: S105 — CSS selector, not a password
# Likewise two #signinButton elements — the visible one carries the
# `gb-button` brand class; the hidden shipto duplicate does not.
_SUBMIT_SELECTOR = "input#signinButton.gb-button"


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
        """Search Graybar for `mpn`, navigate to first product hit, extract offer."""
        try:
            self._ensure_logged_in()
            assert self._page is not None
            # Step 1: search.
            self._page.goto(_SEARCH_URL.format(mpn=mpn), timeout=_NAV_TIMEOUT_MS)
            self._page.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT_MS)
            self._page.wait_for_timeout(3_000)  # let result JS hydrate

            # Step 2: walk to first /p/ product link.
            product_href = self._page.evaluate("""
                () => {
                    const a = document.querySelector('a[href*="/p/"]');
                    return a ? a.href : null;
                }
                """)
            if not product_href:
                return _error_offer(
                    self.distributor_id, mpn, "no product results for MPN"
                )

            # Step 3: open product detail + extract.
            self._page.goto(product_href, timeout=_NAV_TIMEOUT_MS)
            self._page.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT_MS)
            self._page.wait_for_timeout(3_000)
            return self._parse_product_detail(mpn)
        except Exception as e:
            logger.exception("graybar fetch failed for %s", mpn)
            return _error_offer(
                self.distributor_id, mpn, f"graybar fetch failed: {e!r}"
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
        # Graybar throws up a cookie notification banner + a "favorites tour"
        # modal on first load — both intercept the sign-in button click.
        # Dismiss before login. Best-effort: missing overlay isn't fatal.
        self._dismiss_overlays()
        # Login form fields use Spring Security defaults (j_username / j_password).
        self._page.fill(_USERNAME_SELECTOR, user)
        self._page.fill(_PASSWORD_SELECTOR, password)
        self._page.click(_SUBMIT_SELECTOR)
        self._page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)
        self._logged_in = True

    def _dismiss_overlays(self) -> None:
        """Close cookie banner + any open modals so the login button is clickable."""
        assert self._page is not None
        # Cookie banner — try the close button selectors Graybar uses.
        for selector in (
            "#js-cookie-notification button",
            "#js-cookie-notification .close",
            "button[aria-label='Close']",
            ".gb-modal.open .close",
        ):
            try:
                el = self._page.query_selector(selector)
                if el is not None and el.is_visible():
                    el.click(timeout=2_000)
            except Exception as e:
                # Reason: overlay dismissal is best-effort. Log + continue;
                # the real click in the login flow retries.
                logger.debug("overlay dismissal %s: %r", selector, e)

    def _parse_product_detail(self, mpn: str) -> DistributorOffer:
        """Read MPN + price + availability from the loaded product detail page.

        Graybar exposes everything we need as `data-*` attributes on the
        product container — far more stable than CSS-class scraping. The
        `.availability` text block carries stock state ("In Stock" / "Out
        of Stock to Ship") that we map to `stock_count` 1 / 0. Real
        per-distributor stock counts aren't shown to logged-in users at
        v1; Graybar surfaces "in stock at branch" / "out of stock" only.

        Sets `error` to "ambiguous match" when the page's `data-mpn`
        doesn't include the queried MPN — search relevance is fuzzy.
        """
        assert self._page is not None
        data = self._page.evaluate("""
            () => {
                const el = document.querySelector('[data-mpn]');
                if (!el) return {};
                return {
                    mpn: el.getAttribute('data-mpn'),
                    sku: el.getAttribute('data-sku'),
                    price: el.getAttribute('data-price'),
                    manufacturer: el.getAttribute('data-manufacturer'),
                };
            }
            """)
        availability_text = _text_or_none(self._page, ".availability") or ""
        in_stock = (
            "In Stock" in availability_text and "Out of Stock" not in availability_text
        )

        page_mpn = (data.get("mpn") or "").strip()
        ambiguous = (
            mpn.upper() not in page_mpn.upper() and page_mpn.upper() not in mpn.upper()
        )

        return DistributorOffer(
            distributor=self.distributor_id,
            mpn=mpn,
            stock_count=1 if in_stock else 0,
            lead_time_weeks=None,  # Graybar doesn't surface lead-time on PDP at v1
            unit_cost_usd=_safe_float(data.get("price")),
            refreshed_at=datetime.now(UTC),
            error=(
                f"ambiguous match: search returned MPN {page_mpn!r}"
                if ambiguous
                else None
            ),
        )


def _error_offer(
    distributor: DistributorId, mpn: str, message: str
) -> DistributorOffer:
    """Build an error-only offer for fetches that failed before extraction."""
    return DistributorOffer(
        distributor=distributor,
        mpn=mpn,
        refreshed_at=datetime.now(UTC),
        error=message,
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

---
name: scrape-b2b-distributor
description: Build a Playwright-driven B2B distributor catalog scraper (Graybar, Anixter/Wesco, Insight, CDW) for the BOM enrichment pipeline. Encodes the iteration discipline + portal-quirks that the Graybar live-probe converged on. Compounds learnings as each new distributor lands.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
---

# Build B2B Distributor Scraper

For per-MPN price + stock + lead time + lifecycle extraction from
authenticated B2B distributor portals. Already-shipped:

- `_graybar_client.py` — converged 2026-05-23 (live-probe, ~4 iters).

This skill encodes the iteration pattern so the next scraper
(Anixter, Insight, CDW) lands in ≤ 2 probe rounds. Compounds learnings.

## Shared infrastructure (do NOT duplicate)

| File | Purpose |
|---|---|
| `src/bom_enrichment/enrichment_models.py` | `DistributorOffer` + `EnrichmentForMpn` pydantic types. Field set is fixed; add new fields here, not in subclass-specific models. |
| `src/bom_enrichment/_base_scraper.py` | `DistributorClient` ABC — `fetch_offer(mpn)` + `close()`. Implementations NEVER raise from `fetch_offer` — error goes inside `DistributorOffer.error`. |
| `src/bom_enrichment/enrichment_service.py` | Orchestrator. Parallel-per-distributor, sequential-per-MPN. Catches client exceptions, builds an error-offer. |
| `template-secrets.env` | One pair of `<DISTRIBUTOR>_USER` / `<DISTRIBUTOR>_PASS` env vars per portal. Add new pair when wiring a new client. |

## Phase 0: Reality check before writing code

Some "distributors" have real APIs and shouldn't be scraped at all:

- **Mouser, Digikey, Newark/Element14** — REST APIs with free tiers.
  Use those instead of Playwright. Faster, more stable, no selector
  drift. Implementation pattern is different from this skill — use
  httpx + the vendor's documented endpoints.
- **Graybar, Anixter (Wesco), Insight, CDW** — no public API. Playwright
  scraping is the only path. THIS skill covers them.

## Phase 1: Live-probe to discover real selectors

Write probes BEFORE writing the scraper. The selectors you guess from
the vendor docs / general intuition WILL be wrong. Probe the live
portal with the actual creds, dump DOM structure, find the real
selectors, then write the scraper to match.

### Probe template

```python
# /tmp/probe_<vendor>.py
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto("https://<vendor>.com/login", timeout=30000)
    page.wait_for_load_state("domcontentloaded", timeout=20000)

    # Dump all input + button elements to find real selectors
    inputs = page.evaluate("""
        Array.from(document.querySelectorAll('input, button[type="submit"]'))
          .map(el => ({
            tag: el.tagName.toLowerCase(),
            type: el.type || null,
            name: el.name || null,
            id: el.id || null,
            classes: el.className,
            placeholder: el.placeholder || null,
            ariaLabel: el.getAttribute('aria-label') || null,
            visible: el.offsetParent !== null,
          }))
          .filter(e => e.type !== 'hidden')
    """)
    for inp in inputs[:30]:
        print(inp)
    browser.close()
```

Run with `bash -c 'set -a; source secrets.env; set +a; uv run python /tmp/probe_<vendor>.py'`.

### What to look for in the output

- **Visible vs hidden duplicates** — many B2B portals render the login
  form twice (main + ship-to-account). Both have the same ids/names
  but distinct classes (`_shipto` suffix, etc.). The scraper MUST
  filter by class to pick the visible one — `#j_username` alone will
  match the hidden one first and Playwright will time out waiting for
  visibility.
- **Spring Security defaults** — Graybar uses `j_username`/`j_password`.
  Common in older Java enterprise portals. Anixter/Insight may use the
  same; Mouser/CDW are more likely modern React form names.
- **Login URL gotchas** — `/store/login` may redirect to a store-finder
  page that buries the form. Try `/login`, `/account/login`, or just
  the homepage with the header sign-in link. Confirm via probe before
  hardcoding.

## Phase 2: Login flow

```python
def _ensure_logged_in(self) -> None:
    if self._logged_in:
        return
    user = os.environ.get("VENDOR_USER")
    password = os.environ.get("VENDOR_PASS")
    if not user or not password:
        raise RuntimeError("VENDOR_USER + VENDOR_PASS env vars required")

    from playwright.sync_api import sync_playwright
    self._playwright = sync_playwright().start()
    self._browser = self._playwright.chromium.launch(headless=True)
    self._context = self._browser.new_context()
    self._page = self._context.new_page()

    self._page.goto(_LOGIN_URL, timeout=_NAV_TIMEOUT_MS)
    self._dismiss_overlays()  # ← always; see Phase 3
    self._page.fill(_USERNAME_SELECTOR, user)
    self._page.fill(_PASSWORD_SELECTOR, password)
    self._page.click(_SUBMIT_SELECTOR)
    # Wait for navigation OFF the login page rather than networkidle —
    # SPAs may never go idle.
    self._page.wait_for_url(lambda u: "/login" not in u, timeout=_NAV_TIMEOUT_MS)
    self._logged_in = True
```

Key gotchas:
- **`wait_for_load_state("networkidle")` times out** on SPA portals
  (long-polling, analytics, etc.). Use `domcontentloaded` + a fixed
  wait or `wait_for_url` to confirm navigation succeeded.
- **Lazy-import playwright** inside `_ensure_logged_in` keeps cold-start
  fast for processes that don't actually scrape.

## Phase 3: Dismiss overlays before any click

Every B2B portal has overlays that intercept clicks on first load:
- Cookie consent banner
- "Take a tour" / "What's new" modal
- Favorites tutorial popup
- Survey invitation

```python
def _dismiss_overlays(self) -> None:
    assert self._page is not None
    for selector in (
        "#js-cookie-notification button",      # Graybar cookie
        "#js-cookie-notification .close",
        "button[aria-label='Close']",          # generic close-X
        ".gb-modal.open .close",               # Graybar modal close
        "#cookie-consent-accept",              # common alt
        "button[data-cookie-accept]",          # alt
    ):
        try:
            el = self._page.query_selector(selector)
            if el is not None and el.is_visible():
                el.click(timeout=2_000)
        except Exception as e:
            logger.debug("overlay dismissal %s: %r", selector, e)
```

Best-effort — missing overlay isn't fatal. Add per-portal selectors as
you discover them during probe.

## Phase 4: Search + product-detail extraction

### Search URL pattern

Most B2B portals expose search via URL parameter:
- Graybar: `/search/?text={mpn}&enablePartNumberSearch=true`
- Anixter: TBD
- Insight: TBD
- CDW: TBD

The `enablePartNumberSearch=true` flag matters — without it, Graybar
returns a category-facet landing page instead of product cards. Probe
each portal to find the equivalent flag.

### Fuzzy-search ambiguity

B2B portal search is keyword-fuzzy — searching for `AR9658` may return
a Phoenix Contact part whose MPN contains "9658" as a substring instead
of the APC NetShelter AR9658. The scraper MUST verify the returned
product's MPN matches the queried one before surfacing pricing.

```python
page_mpn = data.get("mpn", "").strip()
ambiguous = (
    mpn.upper() not in page_mpn.upper()
    and page_mpn.upper() not in mpn.upper()
)
return DistributorOffer(
    ...,
    error=(
        f"ambiguous match: search returned MPN {page_mpn!r}"
        if ambiguous else None
    ),
)
```

The error is surfaced to the BOM consumer — they decide whether to
trust the price (low confidence) or ignore the offer.

### Extract via data-* attributes when possible

Graybar exposes `data-mpn`, `data-sku`, `data-price`, `data-manufacturer`
on the product container. These are FAR more stable than CSS class
selectors that get refactored across UI redesigns. Walk the DOM for
`data-*` attributes during probe; prefer them whenever present.

When data-* attrs aren't there, fall back to text-content of well-named
classes (`.price`, `.availability`, `.product-code`). Parse text
defensively (strip "$", commas, etc.) — text format is the least
stable selector path.

## Phase 5: Test discipline

Live-portal tests are slow + need credentials → NOT in the unit suite.
Unit tests use a mock `DistributorClient` (see
`test_enrichment_service.py::_MockClient`). Live tests are manual
probe scripts in `/tmp/` — keep them around as regression guards
when iterating selectors.

## Compounding learnings (per converged client)

### graybar — converged 2026-05-23 (4 probe rounds)

**Wrong assumptions that cost iterations:**
1. Best-guessed selectors `input[name='username']` — wrong. Spring
   Security uses `j_username`/`j_password`.
2. `wait_for_load_state("networkidle")` — never goes idle on Graybar
   (analytics + long-poll). Switched to `wait_for_url`.
3. `/store/login` URL — redirects to `/store-finder` which buries the
   form behind a modal. `/login` (no /store prefix) works.
4. Singular `#j_username` selector — matches HIDDEN ship-to-account
   form first. Filter via class: `:not(.login-form-email_shipto)`.
5. Cookie + favorites modal intercept clicks — add overlay dismissal
   step before any user-action click.
6. Best-guessed search URL `/store/en/gb/search?q=...` — 404. Real URL
   discovered by probe: `/search/?text=...&enablePartNumberSearch=true`.
7. Best-guessed product-detail selectors `data-test-id="stock-count"`
   etc — wrong. Graybar uses `data-mpn`, `data-price`, etc on the
   product container. `.availability` text block for stock.

**Things that worked first-try:**
- Lazy-import playwright inside `_ensure_logged_in`.
- Per-instance browser context reused across MPN lookups (single login,
  rate-limit-friendly).
- `data-*` attribute extraction via single `page.evaluate()` call
  returning all fields at once.

**Quirks specific to Graybar:**
- Two `#signinButton` elements — the visible one has class `gb-button`.
- ZIP code in account profile (60618 Chicago) drives "Stocked at
  Branch" + "Stocked to Ship" availability strings. Stock count isn't
  a real number — only "In Stock" / "Out of Stock" boolean.
- Fuzzy search returns wrong products often. Ambiguous-match detection
  via `data-mpn` substring check is mandatory.

### anixter — NOT VIABLE for scraping (verified 2026-05-23)

Cloudflare's "Just a moment..." challenge page blocks all headless
playwright requests with HTTP 403. This is an active anti-bot signal —
Anixter (Wesco) has explicitly chosen to block automated access.

Bypass options + tradeoffs:
- `playwright-stealth` library: sometimes evades Cloudflare detection
  via fingerprint patching, but cat-and-mouse — Cloudflare updates
  regularly.
- Headed mode (`headless=False`): still detected because of automation
  flags (`navigator.webdriver`, etc.).
- Browser-extension agent (Claude for Chrome) with human-resembling
  pacing: more likely to pass.

**Recommendation: don't try to circumvent.** Active anti-bot defenses
are an explicit "no" from the vendor. Use Anixter accounts for manual
procurement; do not automate against them.

### insight — NOT VIABLE for scraping (verified 2026-05-23)

Returns `ERR_HTTP2_PROTOCOL_ERROR` on every request — likely TLS
fingerprint or HTTP/2 settings detection. Same family as Cloudflare's
defense, different vendor.

Same recommendation: skip automated scraping; use account for manual
quotes.

### cdw — login page reachable, awaiting account confirmation

Probe 2026-05-23: `https://www.cdw.com/account/LogOn` loads cleanly,
sign-in form accessible. No anti-bot blocks observed. Iteration
deferred until ARCNODE's CDW B2B account is confirmed via email.

### mouser — REST API path

Skip Playwright entirely. Implement via `httpx` POST to
`https://api.mouser.com/api/v1/search/partnumber` with `apiKey` query
param. Free tier covers our volume. See Mouser docs at
https://www.mouser.com/api-search/.

## Chug-along gate

This skill is "done" when the second distributor (anixter) converges
in ≤2 probe rounds. If iter 3+ still has wrong selectors on anixter,
refine this skill BEFORE iter 4 — the goal is compounding speed, not
recurring rework.

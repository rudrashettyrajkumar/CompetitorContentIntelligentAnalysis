"""Best-effort scraping of **public** LinkedIn company pages via Playwright.

Disabled by default. Automated collection from LinkedIn violates its User Agreement
(see ``docs/solution-design.md`` §7). This adapter only runs when BOTH:

- ``collection.allow_scraping: true`` in ``config/app.yaml``, and
- the ``ACKNOWLEDGE_LINKEDIN_TOS`` env var is set to ``true``.

Otherwise construction raises ``ScrapingDisabledError``. There is no login flow;
requests are rate-limited and selectors are best-effort against the logged-out
public HTML.
"""

from __future__ import annotations

import time
from datetime import datetime

from app.config.settings import AppConfig, Settings, get_app_config, get_settings
from app.datasources.base import DataSource, ScrapingDisabledError
from app.schemas.collection import CompanyProfile, RawPost

_COMPLIANCE_MESSAGE = (
    "LinkedIn scraping is disabled. Automated collection from LinkedIn violates its "
    "User Agreement. To enable it you must set BOTH collection.allow_scraping: true in "
    "config/app.yaml AND the ACKNOWLEDGE_LINKEDIN_TOS=true environment variable. "
    "Choice and risk sit with the operator; prefer the mock/import/apify adapters."
)


class PlaywrightAdapter(DataSource):
    name = "playwright"

    def __init__(
        self,
        settings: Settings | None = None,
        app_config: AppConfig | None = None,
        rate_limit_seconds: float = 3.0,
    ) -> None:
        settings = settings or get_settings()
        app_config = app_config or get_app_config()
        allow_scraping = bool(app_config.collection.get("allow_scraping", False))
        acknowledged = bool(settings.acknowledge_linkedin_tos)
        if not (allow_scraping and acknowledged):
            raise ScrapingDisabledError(_COMPLIANCE_MESSAGE)
        self.rate_limit_seconds = rate_limit_seconds
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.rate_limit_seconds - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _page_html(self, url: str) -> str:
        self._throttle()
        from playwright.sync_api import sync_playwright  # imported only when enabled

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                return page.content()
            finally:
                browser.close()

    def fetch_company_profile(self, linkedin_url: str) -> CompanyProfile:
        html = self._page_html(linkedin_url)
        from bs4 import BeautifulSoup  # optional dep, only on the enabled path

        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        name = title.get_text(strip=True).split("|")[0].strip() if title else None
        desc_tag = soup.find("meta", attrs={"name": "description"})
        description = desc_tag.get("content") if desc_tag else None
        return CompanyProfile(name=name, linkedin_url=linkedin_url, description=description)

    def fetch_posts(self, linkedin_url: str, since: datetime) -> list[RawPost]:
        # The logged-out company page exposes very little post content. Best-effort:
        # return nothing rather than guess. Operators who need real post history should
        # use the apify or import adapter.
        self._page_html(linkedin_url.rstrip("/") + "/posts/")
        return []

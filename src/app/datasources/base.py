"""``DataSource`` abstraction + factory.

Every collection backend implements the same two methods so the collector never
cares which one is active. The active adapter is chosen by ``collection.adapter`` in
``config/app.yaml`` (default ``mock``); the analysis period comes from
``collection.period_days`` and must be one of {7, 10, 30, 60, 90}.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.config.settings import AppConfig, Settings, get_app_config, get_settings
from app.schemas.collection import CompanyProfile, RawPost

VALID_PERIODS = (7, 10, 30, 60, 90)


class ScrapingDisabledError(RuntimeError):
    """Raised when the Playwright adapter is used without explicit opt-in."""


def validate_period_days(value: int) -> int:
    if value not in VALID_PERIODS:
        raise ValueError(f"period_days must be one of {list(VALID_PERIODS)}, got {value!r}")
    return value


class DataSource(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_company_profile(self, linkedin_url: str) -> CompanyProfile: ...

    @abstractmethod
    def fetch_posts(self, linkedin_url: str, since: datetime) -> list[RawPost]: ...


def get_datasource(
    name: str | None = None,
    settings: Settings | None = None,
    app_config: AppConfig | None = None,
) -> DataSource:
    """Build the adapter identified by ``name`` (defaults to ``collection.adapter``)."""
    settings = settings or get_settings()
    app_config = app_config or get_app_config()
    adapter_name = (name or app_config.collection.get("adapter", "mock")).lower()

    # Imported lazily to keep optional deps (httpx clients, playwright) off the
    # import path unless the adapter is actually requested.
    if adapter_name == "mock":
        from app.datasources.mock import MockAdapter

        return MockAdapter()
    if adapter_name in {"import", "imports"}:
        from app.datasources.imports import ImportAdapter

        return ImportAdapter()
    if adapter_name == "apify":
        from app.datasources.apify import ApifyAdapter

        return ApifyAdapter(settings=settings, app_config=app_config)
    if adapter_name == "playwright":
        from app.datasources.playwright_adapter import PlaywrightAdapter

        return PlaywrightAdapter(settings=settings, app_config=app_config)
    raise ValueError(f"Unknown datasource adapter: {name!r}")


def resolve_period_days(override: int | None = None, app_config: AppConfig | None = None) -> int:
    """Per-run override wins; otherwise fall back to config. Always validated."""
    app_config = app_config or get_app_config()
    value = override if override is not None else app_config.collection.get("period_days", 30)
    return validate_period_days(int(value))

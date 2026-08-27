"""Pluggable LinkedIn data collection adapters (EPIC-02)."""

from app.datasources.base import (
    VALID_PERIODS,
    DataSource,
    ScrapingDisabledError,
    get_datasource,
    resolve_period_days,
    validate_period_days,
)

__all__ = [
    "VALID_PERIODS",
    "DataSource",
    "ScrapingDisabledError",
    "get_datasource",
    "resolve_period_days",
    "validate_period_days",
]

import pytest

from app.config.settings import AppConfig, Settings
from app.datasources.base import ScrapingDisabledError, get_datasource
from app.datasources.playwright_adapter import PlaywrightAdapter


def _settings(ack: bool) -> Settings:
    return Settings(acknowledge_linkedin_tos=ack, _env_file=None)


def test_disabled_by_default():
    with pytest.raises(ScrapingDisabledError, match="LinkedIn scraping is disabled"):
        PlaywrightAdapter(settings=_settings(False), app_config=AppConfig(collection={}))


def test_config_flag_alone_is_not_enough():
    with pytest.raises(ScrapingDisabledError):
        PlaywrightAdapter(
            settings=_settings(False),
            app_config=AppConfig(collection={"allow_scraping": True}),
        )


def test_env_ack_alone_is_not_enough():
    with pytest.raises(ScrapingDisabledError):
        PlaywrightAdapter(
            settings=_settings(True),
            app_config=AppConfig(collection={"allow_scraping": False}),
        )


def test_both_flags_construct_ok():
    adapter = PlaywrightAdapter(
        settings=_settings(True),
        app_config=AppConfig(collection={"allow_scraping": True}),
    )
    assert adapter.name == "playwright"


def test_factory_respects_the_guard():
    with pytest.raises(ScrapingDisabledError):
        get_datasource(
            "playwright",
            settings=_settings(False),
            app_config=AppConfig(collection={"allow_scraping": True}),
        )

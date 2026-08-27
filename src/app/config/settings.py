"""Application settings: env vars (secrets/runtime) + YAML config (app + models)."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPTS_DIR = PROJECT_ROOT / "prompts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: str = ""
    nvidia_api_key: str = ""
    groq_api_key: str = ""
    llm_fake_mode: bool = False
    database_url: str = "sqlite:///data/app.db"
    log_level: str = "INFO"
    apify_token: str = ""
    acknowledge_linkedin_tos: bool = False

    @property
    def any_llm_key(self) -> bool:
        return bool(self.openrouter_api_key or self.nvidia_api_key or self.groq_api_key)


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str
    rpm: int = 20


class ModelsConfig(BaseModel):
    provider_order: list[str]
    providers: dict[str, ProviderConfig]
    tiers: dict[str, dict[str, list[str]]]

    @field_validator("provider_order")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("provider_order must not be empty")
        return v

    def models_for(self, tier: str) -> list[tuple[str, str]]:
        """Ordered (provider, model_id) attempts for a tier, following provider_order."""
        if tier not in self.tiers:
            raise KeyError(f"Unknown model tier: {tier!r}")
        tier_map = self.tiers[tier]
        return [
            (provider, model_id)
            for provider in self.provider_order
            for model_id in tier_map.get(provider, [])
        ]


class AppConfig(BaseModel):
    collection: dict = {}
    llm: dict = {}
    engagement: dict = {}
    analysis: dict = {}
    campaigns: dict = {}
    cross: dict = {}
    loop: dict = {}
    format_groups: dict = {}
    strategy: dict = {}
    company: dict = {}


class Taxonomies(BaseModel):
    """Configured classification vocabularies (config/taxonomies.yaml)."""

    formats: list[str]
    topics: list[str]
    cta_types: list[str]
    keyword_categories: list[str]


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_models_config(path: Path | None = None) -> ModelsConfig:
    return ModelsConfig.model_validate(_load_yaml(path or CONFIG_DIR / "models.yaml"))


@lru_cache
def get_app_config(path: Path | None = None) -> AppConfig:
    return AppConfig.model_validate(_load_yaml(path or CONFIG_DIR / "app.yaml"))


@lru_cache
def get_taxonomies(path: Path | None = None) -> Taxonomies:
    return Taxonomies.model_validate(_load_yaml(path or CONFIG_DIR / "taxonomies.yaml"))

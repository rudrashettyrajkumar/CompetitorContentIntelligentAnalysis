from pathlib import Path

import pytest

from app.config.settings import PROMPTS_DIR, ModelsConfig, Settings
from app.core.model_router import FakeLLM, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.engine import build_engine, build_session_factory, init_db

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        llm_fake_mode=True,
        database_url="sqlite:///:memory:",
        _env_file=None,
    )


@pytest.fixture
def models_config() -> ModelsConfig:
    return ModelsConfig.model_validate(
        {
            "provider_order": ["openrouter", "nvidia", "groq"],
            "providers": {
                "openrouter": {
                    "base_url": "https://openrouter.test/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "rpm": 20,
                },
                "nvidia": {
                    "base_url": "https://nvidia.test/v1",
                    "api_key_env": "NVIDIA_API_KEY",
                    "rpm": 40,
                },
                "groq": {
                    "base_url": "https://groq.test/v1",
                    "api_key_env": "GROQ_API_KEY",
                    "rpm": 30,
                },
            },
            "tiers": {
                "fast": {
                    "openrouter": ["openrouter/fast-model:free"],
                    "nvidia": ["nvidia/fast-model"],
                    "groq": ["groq/fast-model"],
                },
                "reasoning": {"openrouter": ["openrouter/reasoning-model:free"]},
            },
        }
    )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_router(settings, models_config, fake_llm) -> ModelRouter:
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


@pytest.fixture
def prompt_registry() -> PromptRegistry:
    return PromptRegistry(PROMPTS_DIR)


@pytest.fixture
def db_session():
    engine = build_engine("sqlite:///:memory:")
    init_db(engine)
    factory = build_session_factory(engine)
    session = factory()
    yield session
    session.close()
    engine.dispose()

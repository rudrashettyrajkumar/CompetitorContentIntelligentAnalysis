import pytest

from app.config.settings import ModelsConfig, Settings, get_app_config, get_models_config


def test_settings_defaults_without_env(monkeypatch):
    monkeypatch.delenv("LLM_FAKE_MODE", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_fake_mode is False
    assert s.database_url.startswith("sqlite:///")
    assert s.any_llm_key is False


def test_any_llm_key():
    assert Settings(openrouter_api_key="x", _env_file=None).any_llm_key is True


def test_real_models_config_loads():
    cfg = get_models_config()
    assert cfg.provider_order[0] == "openrouter"
    attempts = cfg.models_for("fast")
    assert attempts, "fast tier must have models"
    providers = [p for p, _ in attempts]
    # fallback order preserved: all openrouter attempts before nvidia before groq
    assert providers == sorted(providers, key=cfg.provider_order.index)


def test_models_for_unknown_tier_raises(models_config: ModelsConfig):
    with pytest.raises(KeyError):
        models_config.models_for("nope")


def test_real_app_config_loads():
    cfg = get_app_config()
    assert cfg.collection["adapter"] == "mock"
    assert cfg.engagement["weights"]["reposts"] == 3

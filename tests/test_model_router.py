import pytest

from app.core.model_router import (
    AllProvidersFailedError,
    LLMOutputError,
    ModelRouter,
    extract_json,
    is_retryable,
)
from app.schemas import EchoResult


class RateLimitError(Exception):
    status_code = 429


class AuthError(Exception):
    status_code = 401


class _Response:
    def __init__(self, content: str):
        self.content = content


class ScriptedChat:
    """Fake chat model: each invoke pops the next scripted item (str or Exception)."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Response(item)


def make_router(settings, models_config, chats: dict[str, ScriptedChat], **kwargs):
    """chats keyed by provider name; same chat reused for every call to that provider."""

    def factory(provider_cfg, model_id, api_key, temperature):
        for name, cfg in models_config.providers.items():
            if cfg.base_url == provider_cfg.base_url:
                return chats[name]
        raise AssertionError("unknown provider")

    return ModelRouter(settings, models_config, chat_factory=factory, backoff_base=0, **kwargs)


@pytest.fixture
def live_settings(settings):
    return settings.model_copy(
        update={
            "llm_fake_mode": False,
            "openrouter_api_key": "or-key",
            "nvidia_api_key": "nv-key",
            "groq_api_key": "gq-key",
        }
    )


VALID = '{"message": "hi", "language": "en"}'


def test_fake_mode_returns_validated_schema(fake_router, fake_llm):
    fake_llm.register(EchoResult, {"message": "hello", "language": "fr"})
    result = fake_router.invoke(
        tier="fast", system="s", user="u", schema=EchoResult, prompt_name="echo"
    )
    assert isinstance(result, EchoResult)
    assert result.language == "fr"
    assert fake_llm.calls[0]["schema"] == "EchoResult"


def test_fallback_to_nvidia_on_persistent_429(live_settings, models_config):
    chats = {
        "openrouter": ScriptedChat([RateLimitError(), RateLimitError(), RateLimitError()]),
        "nvidia": ScriptedChat([VALID]),
        "groq": ScriptedChat([]),
    }
    router = make_router(live_settings, models_config, chats)
    result = router.invoke(tier="fast", system="s", user="u", schema=EchoResult)
    assert result.message == "hi"
    assert chats["openrouter"].calls == 3  # exhausted retries
    assert chats["nvidia"].calls == 1
    assert chats["groq"].calls == 0


def test_retry_within_provider_recovers(live_settings, models_config):
    chats = {
        "openrouter": ScriptedChat([RateLimitError(), VALID]),
        "nvidia": ScriptedChat([]),
        "groq": ScriptedChat([]),
    }
    router = make_router(live_settings, models_config, chats)
    result = router.invoke(tier="fast", system="s", user="u", schema=EchoResult)
    assert result.message == "hi"
    assert chats["openrouter"].calls == 2
    assert chats["nvidia"].calls == 0


def test_non_retryable_error_falls_through_immediately(live_settings, models_config):
    chats = {
        "openrouter": ScriptedChat([AuthError()]),
        "nvidia": ScriptedChat([VALID]),
        "groq": ScriptedChat([]),
    }
    router = make_router(live_settings, models_config, chats)
    router.invoke(tier="fast", system="s", user="u", schema=EchoResult)
    assert chats["openrouter"].calls == 1


def test_provider_without_key_is_skipped(live_settings, models_config):
    no_or_key = live_settings.model_copy(update={"openrouter_api_key": ""})
    chats = {
        "openrouter": ScriptedChat([VALID]),
        "nvidia": ScriptedChat([VALID]),
        "groq": ScriptedChat([]),
    }
    router = make_router(no_or_key, models_config, chats)
    router.invoke(tier="fast", system="s", user="u", schema=EchoResult)
    assert chats["openrouter"].calls == 0
    assert chats["nvidia"].calls == 1


def test_all_providers_failed(live_settings, models_config):
    chats = {
        "openrouter": ScriptedChat([AuthError()]),
        "nvidia": ScriptedChat([AuthError()]),
        "groq": ScriptedChat([AuthError()]),
    }
    router = make_router(live_settings, models_config, chats)
    with pytest.raises(AllProvidersFailedError):
        router.invoke(tier="fast", system="s", user="u", schema=EchoResult)


def test_repair_path_recovers_invalid_json(live_settings, models_config):
    chats = {
        "openrouter": ScriptedChat(["not json at all", f"```json\n{VALID}\n```"]),
        "nvidia": ScriptedChat([]),
        "groq": ScriptedChat([]),
    }
    router = make_router(live_settings, models_config, chats)
    result = router.invoke(tier="fast", system="s", user="u", schema=EchoResult)
    assert result.message == "hi"
    assert chats["openrouter"].calls == 2


def test_twice_invalid_raises_output_error_without_fallback(live_settings, models_config):
    chats = {
        "openrouter": ScriptedChat(["garbage", '{"wrong": true}']),
        "nvidia": ScriptedChat([VALID]),
        "groq": ScriptedChat([]),
    }
    router = make_router(live_settings, models_config, chats)
    with pytest.raises(LLMOutputError):
        router.invoke(tier="fast", system="s", user="u", schema=EchoResult)
    assert chats["nvidia"].calls == 0  # schema failure must not burn other providers


def test_fake_llm_repair_via_queue(fake_router, fake_llm):
    fake_llm.enqueue("nonsense")
    fake_llm.enqueue(VALID)
    result = fake_router.invoke(tier="fast", system="s", user="u", schema=EchoResult)
    assert result.message == "hi"
    assert len(fake_llm.calls) == 2


def test_extract_json_variants():
    assert extract_json(VALID) == VALID
    assert extract_json(f"Sure! Here you go:\n```json\n{VALID}\n```").strip() == VALID
    assert extract_json(f"The answer is {VALID} hope that helps") == VALID
    assert extract_json('[{"a": 1}]') == '[{"a": 1}]'


def test_is_retryable():
    assert is_retryable(RateLimitError())
    assert not is_retryable(AuthError())
    assert not is_retryable(ValueError("x"))

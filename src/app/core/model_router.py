"""Single gateway for every LLM call.

Fallback chain: OpenRouter (free models) -> NVIDIA NIM -> Groq, in the order given by
config/models.yaml. Each attempt gets bounded retries with exponential backoff on
rate-limit/5xx errors; any other transport failure falls through to the next
(provider, model) pair. All responses are validated against a Pydantic schema, with one
repair round-trip on invalid output.

Feature code must never instantiate chat models directly — always go through
ModelRouter.invoke().
"""

import json
import re
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import ModelsConfig, ProviderConfig, Settings
from app.core.logging import get_logger

log = get_logger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMError(Exception):
    pass


class LLMOutputError(LLMError):
    """The model responded, but its output failed schema validation twice."""


class AllProvidersFailedError(LLMError):
    def __init__(self, errors: list[tuple[str, str, Exception]]):
        self.errors = errors
        detail = "; ".join(f"{p}/{m}: {type(e).__name__}: {e}" for p, m, e in errors)
        super().__init__(f"All LLM providers failed: {detail or 'no providers configured'}")


def is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status in RETRYABLE_STATUS:
        return True
    return "ratelimit" in type(exc).__name__.lower()


def extract_json(text: str) -> str:
    """Pull a JSON object/array out of a model response (fenced or embedded)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if text.startswith(("{", "[")):
        return text
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            return text[start : end + 1]
    return text


class FakeLLM:
    """Deterministic offline backend for tests and `make demo`.

    Responses come from an explicit queue (highest priority) or from per-schema
    registrations. Every call is recorded in `calls` so tests can assert batching.
    """

    def __init__(self) -> None:
        self._by_schema: dict[str, Any] = {}
        self._queue: deque[str] = deque()
        self.calls: list[dict[str, str]] = []

    def register(self, schema: type[BaseModel], response: Any) -> None:
        """response: dict | BaseModel | str | callable(system, user) -> any of those."""
        self._by_schema[schema.__name__] = response

    def enqueue(self, raw_text: str) -> None:
        self._queue.append(raw_text)

    def invoke(self, system: str, user: str, schema: type[BaseModel]) -> str:
        self.calls.append({"system": system, "user": user, "schema": schema.__name__})
        if self._queue:
            return self._queue.popleft()
        response = self._by_schema.get(schema.__name__)
        if response is None:
            raise LLMError(f"FakeLLM has no response registered for schema {schema.__name__!r}")
        if callable(response):
            response = response(system, user)
        if isinstance(response, BaseModel):
            return response.model_dump_json()
        if isinstance(response, (dict, list)):
            return json.dumps(response)
        return str(response)


def _default_chat_factory(
    provider: ProviderConfig, model_id: str, api_key: str, temperature: float
):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=provider.base_url,
        api_key=api_key,
        model=model_id,
        temperature=temperature,
        timeout=90,
        max_retries=0,  # retries/backoff are ModelRouter's job
    )


class ModelRouter:
    def __init__(
        self,
        settings: Settings,
        models_config: ModelsConfig,
        chat_factory: Callable[[ProviderConfig, str, str, float], Any] | None = None,
        fake_llm: FakeLLM | None = None,
        max_attempts: int = 3,
        backoff_base: float = 0.5,
    ) -> None:
        self.settings = settings
        self.models_config = models_config
        self.chat_factory = chat_factory or _default_chat_factory
        self.fake_llm = fake_llm or FakeLLM()
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base

    @property
    def use_fake(self) -> bool:
        return self.settings.llm_fake_mode or not self.settings.any_llm_key

    def chat_model_for(self, tier: str, *, temperature: float = 0.4) -> Any:
        """A ready LangChain chat model for the first configured+keyed provider in ``tier``.

        Used by the deepagents-based campaign/strategy agents, which need a real model
        object rather than the router's validate-and-repair ``invoke`` path. Raises in
        fake mode — those agents run a scripted stub offline instead.
        """
        if self.use_fake:
            raise LLMError("chat_model_for is unavailable in fake mode")
        for provider_name, model_id in self.models_config.models_for(tier):
            provider = self.models_config.providers[provider_name]
            api_key = getattr(self.settings, provider.api_key_env.lower(), "")
            if api_key:
                return self.chat_factory(provider, model_id, api_key, temperature)
        raise AllProvidersFailedError([])

    def invoke(
        self,
        *,
        tier: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        temperature: float = 0.2,
        prompt_name: str = "adhoc",
        prompt_version: int = 1,
    ) -> BaseModel:
        started = time.monotonic()
        if self.use_fake:
            result = self._parse_with_repair(
                lambda s, u: self.fake_llm.invoke(s, u, schema), system, user, schema
            )
            self._log_call(prompt_name, prompt_version, tier, "fake", "fake", started, 0)
            return result

        errors: list[tuple[str, str, Exception]] = []
        for provider_name, model_id in self.models_config.models_for(tier):
            provider = self.models_config.providers[provider_name]
            api_key = getattr(self.settings, provider.api_key_env.lower(), "")
            if not api_key:
                log.debug("provider_skipped_no_key", provider=provider_name)
                continue
            chat = self.chat_factory(provider, model_id, api_key, temperature)
            retries = 0

            def call(s: str, u: str, _chat=chat) -> str:
                nonlocal retries
                for attempt in Retrying(
                    retry=retry_if_exception(is_retryable),
                    stop=stop_after_attempt(self.max_attempts),
                    wait=wait_exponential(multiplier=self.backoff_base, max=8),
                    reraise=True,
                ):
                    with attempt:
                        retries = attempt.retry_state.attempt_number - 1
                        return self._chat_text(_chat, s, u)
                raise LLMError("unreachable")

            try:
                result = self._parse_with_repair(call, system, user, schema)
            except LLMOutputError:
                raise  # model answered but can't produce the schema — don't burn quota on fallbacks
            except Exception as exc:  # noqa: BLE001 — any transport failure falls through
                errors.append((provider_name, model_id, exc))
                log.warning(
                    "provider_failed",
                    provider=provider_name,
                    model=model_id,
                    error=str(exc),
                    prompt=prompt_name,
                )
                continue
            self._log_call(
                prompt_name, prompt_version, tier, provider_name, model_id, started, retries
            )
            return result
        raise AllProvidersFailedError(errors)

    @staticmethod
    def _chat_text(chat: Any, system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = chat.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return response.content if hasattr(response, "content") else str(response)

    def _parse_with_repair(
        self,
        call: Callable[[str, str], str],
        system: str,
        user: str,
        schema: type[BaseModel],
    ) -> BaseModel:
        text = call(system, user)
        try:
            return schema.model_validate_json(extract_json(text))
        except (ValidationError, ValueError) as first_error:
            repair_user = (
                f"{user}\n\nYour previous response was not valid for the required JSON "
                f"schema. Error: {first_error}\n"
                f"Previous response: {text[:2000]}\n"
                "Respond again with ONLY valid JSON matching the schema."
            )
            repaired = call(system, repair_user)
            try:
                return schema.model_validate_json(extract_json(repaired))
            except (ValidationError, ValueError) as second_error:
                raise LLMOutputError(
                    f"Output failed validation for {schema.__name__} after repair: {second_error}"
                ) from second_error

    @staticmethod
    def _log_call(
        prompt_name: str,
        prompt_version: int,
        tier: str,
        provider: str,
        model: str,
        started: float,
        retries: int,
    ) -> None:
        log.info(
            "llm_call",
            prompt=prompt_name,
            version=prompt_version,
            tier=tier,
            provider=provider,
            model=model,
            latency_ms=round((time.monotonic() - started) * 1000),
            retries=retries,
        )

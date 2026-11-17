"""Hız sınırı, anahtar sırası ve yedek model."""

import json
import time

import pytest
from langchain_core.runnables import RunnableLambda

from config import (
    bind_agent_model,
    get_chat_model,
    get_rate_limiter,
    get_settings,
    next_gemini_key,
    reset_llm_runtime,
    resilient_chain,
)


def _gemini(monkeypatch, **env):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", env.pop("GEMINI_API_KEY", "test-key"))
    monkeypatch.setenv("GEMINI_MODEL", env.pop("GEMINI_MODEL", "gemini-3.8-flash"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    reset_llm_runtime()


def test_rate_limiter_holds_the_shared_bucket_under_the_free_tier(monkeypatch):
    _gemini(monkeypatch, LLM_RPM="4")
    limiter = get_rate_limiter(get_settings().rpm)
    assert limiter is get_rate_limiter(4)
    assert limiter.requests_per_second == pytest.approx(4 / 60)
    assert limiter.max_bucket_size == 1
    assert limiter.acquire(blocking=False) is False

    model = get_chat_model(get_settings())
    assert model.rate_limiter is limiter


def test_single_key_stays_on_gemini_api_key(monkeypatch):
    _gemini(monkeypatch, GEMINI_API_KEY="only-key", GEMINI_API_KEYS="")
    settings = get_settings()
    assert settings.gemini_api_keys == ("only-key",)
    assert settings.api_key == "only-key"
    assert next_gemini_key(settings.gemini_api_keys) == "only-key"
    model = get_chat_model(settings)
    stored = model.openai_api_key
    revealed = stored.get_secret_value() if hasattr(stored, "get_secret_value") else stored
    assert revealed == "only-key"


def test_api_keys_rotate_round_robin(monkeypatch):
    _gemini(monkeypatch, GEMINI_API_KEY="legacy-key", GEMINI_API_KEYS="key-a, key-b, key-c")
    settings = get_settings()
    assert settings.gemini_api_keys == ("key-a", "key-b", "key-c")
    assert settings.api_key == "key-a"
    model = get_chat_model(settings)
    assert callable(model.openai_api_key)
    reset_llm_runtime()
    assert [model.openai_api_key() for _ in range(4)] == ["key-a", "key-b", "key-c", "key-a"]


def test_fallback_uses_the_saved_temperature(monkeypatch):
    _gemini(monkeypatch, GEMINI_FALLBACK_MODEL="gemini-3.5-flash-lite")
    from agents import context

    context.CONFIG_PATH.write_text(
        json.dumps(
            {"agents": [{"id": "market", "directive": "Satış metnini kısa tut.", "temperature": 0.4}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temperature = context.agent_temperature("market")
    assert temperature == 0.4

    armed = bind_agent_model(get_settings(), temperature)
    primary = armed.runnable
    fallback = armed.fallbacks[0]
    assert primary.max_attempt_number == 4
    assert primary.wait_exponential_jitter is True
    assert fallback.max_attempt_number == 4
    assert fallback.wait_exponential_jitter is True
    assert primary.bound.model_name == "gemini-3.8-flash"
    assert fallback.bound.model_name == "gemini-3.5-flash-lite"
    assert primary.bound.temperature == 0.4
    assert fallback.bound.temperature == 0.4
    assert primary.bound.rate_limiter is not fallback.bound.rate_limiter
    assert fallback.bound.rate_limiter.requests_per_second == pytest.approx(15 / 60)


def test_blank_fallback_model_leaves_only_the_primary(monkeypatch):
    _gemini(monkeypatch, GEMINI_FALLBACK_MODEL="")
    armed = bind_agent_model(get_settings(), 0.0)
    assert armed.max_attempt_number == 4
    assert armed.bound.model_name == "gemini-3.8-flash"


def test_retry_then_fallback_after_rate_limit(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)
    seen = {"primary": 0, "fallback": 0}

    def primary(_payload):
        seen["primary"] += 1
        raise RuntimeError("HTTP 429")

    def fallback(_payload):
        seen["fallback"] += 1
        return "yedek model"

    chain = resilient_chain(RunnableLambda(primary), [RunnableLambda(fallback)])
    assert chain.invoke("merhaba") == "yedek model"
    assert seen["primary"] == 4
    assert seen["fallback"] == 1

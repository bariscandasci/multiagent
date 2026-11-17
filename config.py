"""Ortam değişkenlerinden LLM sağlayıcı ayarlarını okur."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent

OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@dataclass(frozen=True)
class Settings:
    provider: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    gemini_api_key: str
    gemini_base_url: str
    gemini_model: str
    temperature: float
    timeout: float

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key(self) -> str:
        if self.provider == "gemini":
            return self.gemini_api_key
        return self.openai_api_key

    @property
    def base_url(self) -> str:
        if self.provider == "gemini":
            return self.gemini_base_url
        return self.openai_base_url

    @property
    def model(self) -> str:
        if self.provider == "gemini":
            return self.gemini_model
        return self.openai_model


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_settings() -> Settings:
    """`.env` dosyasını okur. Süreçte zaten duran değişkenlerin üzerine yazmaz."""
    load_dotenv(ROOT / ".env", override=False)
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider not in {"openai", "gemini"}:
        provider = "openai"
    return Settings(
        provider=provider,
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", OPENAI_DEFAULT_BASE_URL).strip()
        or OPENAI_DEFAULT_BASE_URL,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_base_url=os.getenv("GEMINI_BASE_URL", GEMINI_DEFAULT_BASE_URL).strip()
        or GEMINI_DEFAULT_BASE_URL,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
        temperature=_float_env("LLM_TEMPERATURE", 0.0),
        timeout=_float_env("LLM_TIMEOUT", 45.0),
    )


def get_chat_model(settings: Settings | None = None):
    """OpenAI SDK uyumlu sohbet modeli. Gemini de aynı istemciyle konuşur."""
    settings = settings or get_settings()
    if not settings.configured:
        raise RuntimeError("LLM api anahtarı tanımlı değil.")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        timeout=settings.timeout,
        max_retries=1,
    )

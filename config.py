"""Ortam değişkenlerinden LLM sağlayıcı ayarlarını okur."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent

OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"
# 3.8 Flash ücretsiz katmanı 5 istek/dakika. Paylaşılan tavan bunun altında kalır.
DEFAULT_RPM = 4.0
DEFAULT_FALLBACK_RPM = 15.0
# 3.7 Flash istekleri 3.8'e yönlendiği için aynı kotayı yer. Lite ayrı kovadadır.
GEMINI_FALLBACK_DEFAULT = "gemini-3.5-flash-lite"
# Gemini 3/4 araç çağrısında bu nesneyi bir sonraki istekte aynen geri ister.
GEMINI_TOOL_EXTRAS = "__gemini_tool_extras__"
# OpenAI strict şemasında olup Gemini function declaration çevirisinin reddettiği anahtarlar.
_GEMINI_SCHEMA_DROP = {
    "additionalProperties",
    "$schema",
    "$id",
    "$defs",
    "definitions",
    "default",
    "title",
    "strict",
}


@dataclass(frozen=True)
class Settings:
    provider: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    gemini_api_key: str
    gemini_api_keys: tuple[str, ...]
    gemini_base_url: str
    gemini_model: str
    gemini_fallback_model: str
    github_token: str
    temperature: float
    timeout: float
    rpm: float
    fallback_rpm: float
    admin_username: str
    admin_password: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key(self) -> str:
        if self.provider == "gemini":
            return self.gemini_api_keys[0] if self.gemini_api_keys else ""
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


def _split_keys(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _gemini_keys_from_env() -> tuple[str, ...]:
    """`GEMINI_API_KEYS` doluysa onu, değilse tek `GEMINI_API_KEY` değerini kullanır."""
    many = _split_keys(os.getenv("GEMINI_API_KEYS", ""))
    if many:
        return many
    single = os.getenv("GEMINI_API_KEY", "").strip()
    return (single,) if single else ()


def _fallback_model_from_env() -> str:
    if "GEMINI_FALLBACK_MODEL" in os.environ:
        return os.environ["GEMINI_FALLBACK_MODEL"].strip()
    return GEMINI_FALLBACK_DEFAULT


def _positive_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return value


def _rpm_from_env() -> float:
    return _positive_env("LLM_RPM", DEFAULT_RPM)


def _fallback_rpm_from_env() -> float:
    return _positive_env("LLM_FALLBACK_RPM", DEFAULT_FALLBACK_RPM)


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
        gemini_api_keys=_gemini_keys_from_env(),
        gemini_base_url=os.getenv("GEMINI_BASE_URL", GEMINI_DEFAULT_BASE_URL).strip()
        or GEMINI_DEFAULT_BASE_URL,
        gemini_model=os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL).strip() or GEMINI_DEFAULT_MODEL,
        gemini_fallback_model=_fallback_model_from_env(),
        github_token=os.getenv("GITHUB_TOKEN", "").strip(),
        temperature=_float_env("LLM_TEMPERATURE", 0.0),
        timeout=_float_env("LLM_TIMEOUT", 45.0),
        rpm=_rpm_from_env(),
        fallback_rpm=_fallback_rpm_from_env(),
        admin_username=os.getenv("ADMIN_USERNAME", "").strip(),
        admin_password=os.getenv("ADMIN_PASSWORD", "").strip(),
    )


def admin_credentials() -> tuple[str, str] | None:
    """İki değer de doluysa Basic Auth açılır. Biri bile boşsa arayüz açık kalır."""
    settings = get_settings()
    if settings.admin_username and settings.admin_password:
        return settings.admin_username, settings.admin_password
    return None


def describe_llm_error(exc: BaseException) -> str:
    """Sağlayıcı hatasının HTTP kodunu ve mesajını, anahtar sızdırmadan döndürür."""
    status = getattr(exc, "status_code", None)
    message = _llm_error_message(exc)
    bits = [type(exc).__name__]
    if status is not None:
        bits.append(f"HTTP {status}")
    if message:
        bits.append(message)
    return ": ".join(bits)


def _llm_error_message(exc: BaseException) -> str:
    from_body = _message_from_body(getattr(exc, "body", None))
    if from_body:
        return from_body[:500]
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()[:500]
    return str(exc)[:500]


def _message_from_body(body: Any) -> str:
    if isinstance(body, list):
        return _message_from_body(body[0]) if body else ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error", body)
    if not isinstance(error, dict):
        return str(error)
    message = str(error.get("message") or "").strip()
    status = str(error.get("status") or "").strip()
    if status and message:
        return f"{status}: {message}"
    return message


def _sanitize_gemini_schema(node: Any) -> Any:
    """Şema anahtarlarını siler; `properties` altındaki alan adlarına dokunmaz."""
    if isinstance(node, list):
        return [_sanitize_gemini_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {
                name: _sanitize_gemini_schema(schema) for name, schema in value.items()
            }
            continue
        if key in _GEMINI_SCHEMA_DROP:
            continue
        cleaned[key] = _sanitize_gemini_schema(value)
    return cleaned


def _sanitize_gemini_tools(tools: list) -> list:
    cleaned = []
    for tool in tools:
        if not isinstance(tool, dict):
            cleaned.append(tool)
            continue
        tool = dict(tool)
        function = tool.get("function")
        if isinstance(function, dict):
            function = {key: value for key, value in function.items() if key != "strict"}
            if "parameters" in function:
                function["parameters"] = _sanitize_gemini_schema(function["parameters"])
            tool["function"] = function
        cleaned.append(tool)
    return cleaned


def _gemini_chat_model():
    """Gemini'nin OpenAI uyumlu ucu için ChatOpenAI alt sınıfı. Sınıf bir kez kurulur."""
    cached = getattr(_gemini_chat_model, "cls", None)
    if cached is not None:
        return cached

    from langchain_core.messages import AIMessage
    from langchain_openai import ChatOpenAI

    class GeminiChatOpenAI(ChatOpenAI):
        """Chat Completions üzerinden Gemini. Responses API ve OpenAI strict şema kullanılmaz."""

        def bind_tools(self, tools, *, strict=None, parallel_tool_calls=None, **kwargs):
            # `strict` alanı Gemini çevirisinde 400 üretir. Varsayılan None bu alanı hiç göndermez.
            return super().bind_tools(tools, strict=None, **kwargs)

        def with_structured_output(self, schema=None, *, method="function_calling", strict=None, **kwargs):
            # json_schema, Gemini'nin reddettiği additionalProperties/strict şemasını üretir.
            if method == "json_schema":
                method = "function_calling"
            return super().with_structured_output(schema, method=method, strict=None, **kwargs)

        def _get_request_payload(self, input_, *, stop=None, **kwargs):
            payload = super()._get_request_payload(input_, stop=stop, **kwargs)
            payload.pop("parallel_tool_calls", None)
            if tools := payload.get("tools"):
                payload["tools"] = _sanitize_gemini_tools(tools)
            messages = self._convert_input(input_).to_messages()
            _replay_tool_extras(payload.get("messages") or [], messages)
            return payload

        def _create_chat_result(self, response, generation_info=None):
            result = super()._create_chat_result(response, generation_info)
            extras = _tool_extras_from_response(response)
            if extras and result.generations:
                message = result.generations[0].message
                if isinstance(message, AIMessage):
                    message.additional_kwargs = {
                        **message.additional_kwargs,
                        GEMINI_TOOL_EXTRAS: extras,
                    }
            return result

    _gemini_chat_model.cls = GeminiChatOpenAI
    return GeminiChatOpenAI


def _tool_extras_from_response(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        raw = response
    elif hasattr(response, "model_dump"):
        raw = response.model_dump(warnings=False)
    else:
        return {}
    try:
        tool_calls = raw["choices"][0]["message"].get("tool_calls") or []
    except (KeyError, IndexError, TypeError, AttributeError):
        return {}
    extras: dict[str, Any] = {}
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        extra = call.get("extra_content")
        call_id = call.get("id")
        if extra and call_id:
            extras[str(call_id)] = extra
    return extras


def _replay_tool_extras(payload_messages: list, lc_messages: list) -> None:
    from langchain_core.messages import AIMessage

    stored: dict[str, Any] = {}
    for message in lc_messages:
        if not isinstance(message, AIMessage):
            continue
        extras = message.additional_kwargs.get(GEMINI_TOOL_EXTRAS) or {}
        if isinstance(extras, dict):
            stored.update(extras)
    if not stored:
        return
    for payload_message in payload_messages:
        if not isinstance(payload_message, dict):
            continue
        for call in payload_message.get("tool_calls") or []:
            extra = stored.get(str(call.get("id")))
            if extra:
                call["extra_content"] = extra


_limiter = None
_limiter_rpm: float | None = None
_fallback_limiter = None
_fallback_limiter_rpm: float | None = None
_key_lock = threading.Lock()
_key_index = 0


def reset_llm_runtime() -> None:
    """Testlerin hız sınırını ve anahtar sırasını sıfırdan kurması için."""
    global _limiter, _limiter_rpm, _fallback_limiter, _fallback_limiter_rpm, _key_index
    with _key_lock:
        _key_index = 0
    _limiter = None
    _limiter_rpm = None
    _fallback_limiter = None
    _fallback_limiter_rpm = None


def get_rate_limiter(rpm: float | None = None):
    """Süreç içi ortak talep kovası. Patlamayı 1 istekte tutar."""
    global _limiter, _limiter_rpm
    from langchain_core.rate_limiters import InMemoryRateLimiter

    pace = DEFAULT_RPM if rpm is None else float(rpm)
    if pace <= 0:
        pace = DEFAULT_RPM
    if _limiter is None or _limiter_rpm != pace:
        _limiter = InMemoryRateLimiter(
            requests_per_second=pace / 60.0,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
        _limiter_rpm = pace
    return _limiter


def get_fallback_rate_limiter(rpm: float | None = None):
    """Yedek modelin kendi kotası. Ana modelin kovasını beklemez."""
    global _fallback_limiter, _fallback_limiter_rpm
    from langchain_core.rate_limiters import InMemoryRateLimiter

    pace = DEFAULT_FALLBACK_RPM if rpm is None else float(rpm)
    if pace <= 0:
        pace = DEFAULT_FALLBACK_RPM
    if _fallback_limiter is None or _fallback_limiter_rpm != pace:
        _fallback_limiter = InMemoryRateLimiter(
            requests_per_second=pace / 60.0,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
        _fallback_limiter_rpm = pace
    return _fallback_limiter


def next_gemini_key(keys: Sequence[str] | None = None) -> str:
    """Birden fazla anahtarı sırayla dağıtır. Tek anahtar hep aynı değeri döndürür."""
    global _key_index
    ring = tuple(keys) if keys is not None else _gemini_keys_from_env()
    if not ring:
        raise RuntimeError("LLM api anahtarı tanımlı değil.")
    if len(ring) == 1:
        return ring[0]
    with _key_lock:
        chosen = ring[_key_index % len(ring)]
        _key_index += 1
        return chosen


def _gemini_api_key(keys: tuple[str, ...]) -> str | Callable[[], str]:
    if len(keys) == 1:
        return keys[0]

    def rotate() -> str:
        return next_gemini_key(keys)

    return rotate


def get_chat_model(
    settings: Settings | None = None,
    *,
    temperature: float | None = None,
    model_name: str | None = None,
    fallback_limiter: bool = False,
):
    """OpenAI SDK uyumlu sohbet modeli. Gemini aynı uçta, Gemini kurallarıyla konuşur."""
    settings = settings or get_settings()
    if not settings.configured:
        raise RuntimeError("LLM api anahtarı tanımlı değil.")
    from langchain_openai import ChatOpenAI

    chosen = settings.temperature if temperature is None else float(temperature)
    name = (model_name or settings.model).strip() or settings.model
    limiter = (
        get_fallback_rate_limiter(settings.fallback_rpm)
        if fallback_limiter
        else get_rate_limiter(settings.rpm)
    )
    # SDK'nın kendi tekrar denemesi with_retry ile çarpılmasın.
    base_url = settings.base_url
    if settings.provider == "gemini":
        base_url = base_url.rstrip("/") + "/"
        model_cls = _gemini_chat_model()
        return model_cls(
            model=name,
            api_key=_gemini_api_key(settings.gemini_api_keys),
            base_url=base_url,
            temperature=chosen,
            timeout=settings.timeout,
            max_retries=0,
            rate_limiter=limiter,
            use_responses_api=False,
        )
    return ChatOpenAI(
        model=name,
        api_key=settings.api_key,
        base_url=base_url,
        temperature=chosen,
        timeout=settings.timeout,
        max_retries=0,
        rate_limiter=limiter,
    )


def resilient_chain(primary, fallbacks: Sequence = ()):
    """Her adayı dört kez, artan bekleme ve jitter ile dener; sonra sıradakine geçer."""
    hardened = [
        item.with_retry(stop_after_attempt=4, wait_exponential_jitter=True)
        for item in (primary, *fallbacks)
    ]
    if len(hardened) == 1:
        return hardened[0]
    return hardened[0].with_fallbacks(list(hardened[1:]))


def bind_agent_model(
    settings: Settings | None = None,
    temperature: float | None = None,
    *,
    tools: list | None = None,
    schema: type | None = None,
):
    """Ajan çağrısı: kayıtlı sıcaklık, hız sınırı, yeniden deneme ve yedek model."""
    settings = settings or get_settings()
    names = [settings.model]
    fallback = settings.gemini_fallback_model.strip() if settings.provider == "gemini" else ""
    if fallback and fallback != settings.model:
        names.append(fallback)
    built = []
    for index, name in enumerate(names):
        model = get_chat_model(
            settings,
            temperature=temperature,
            model_name=name,
            fallback_limiter=index > 0,
        )
        if tools is not None:
            model = model.bind_tools(tools, strict=None)
        if schema is not None:
            model = model.with_structured_output(schema, method="function_calling", strict=None)
        built.append(model)
    return resilient_chain(built[0], built[1:])

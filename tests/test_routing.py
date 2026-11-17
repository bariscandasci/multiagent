"""Yönlendirme kuralları."""

import pytest

from agents.supervisor import _parse_route, heuristic_route


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Personel listesini çıkar", "hr"),
        ("Açık adaylar kimler?", "hr"),
        ("Ayşe Demir hangi departmanda?", "hr"),
        ("Son çeyrek gelir gider özeti", "finance"),
        ("Geciken faturaları listele", "finance"),
        ("Yazılım bütçesi ne durumda?", "finance"),
        ("Sunucu durumunu kontrol et", "ops"),
        ("db-01 neden yavaş", "ops"),
        ("INC-1844 kaydını göster", "ops"),
        ("Merhaba, neler yapabilirsin?", "general"),
        ("rapor hazırla", "general"),
        ("karar verelim", "general"),
    ],
)
def test_keyword_routes(query: str, expected: str):
    assert heuristic_route(query).route == expected


def test_follow_up_stays_with_the_previous_department():
    decision = heuristic_route("peki bunu özetler misin", previous="finance")
    assert decision.route == "finance"
    assert decision.reason == "follow_up"


def test_greeting_does_not_stay_with_the_previous_department():
    decision = heuristic_route("merhaba", previous="finance")
    assert decision.route == "general"
    assert decision.reason == "smalltalk"


def test_tie_without_history_asks_for_clarification():
    decision = heuristic_route("personel faturası")
    assert decision.route == "general"
    assert decision.reason == "ambiguous"


def test_llm_route_json_is_normalized():
    assert _parse_route('```json\n{"route": "finance"}\n```') == "finance"
    assert _parse_route("İK") == "hr"
    assert _parse_route("emin değilim") is None


def test_gemini_client_uses_the_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    from config import get_chat_model, get_settings

    settings = get_settings()
    model = get_chat_model(settings)
    assert settings.model == "gemini-2.5-flash"
    assert model.model_name == "gemini-2.5-flash"
    assert model.openai_api_base.startswith("https://generativelanguage.googleapis.com")


def test_tie_with_history_prefers_the_previous_department():
    decision = heuristic_route("personel faturası", previous="hr")
    assert decision.route == "hr"
    assert decision.reason == "follow_up"

"""Yönlendirme kuralları."""

import pytest

from agents.supervisor import _parse_route, heuristic_route


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Aylık sabit giderleri çıkar", "finance"),
        ("Yeni API maliyetini bütçeye ekle", "finance"),
        ("Bu projeyi hangi sektörlere satabiliriz", "market"),
        ("Satış stratejisi ve müşteri profili çıkar", "market"),
        ("Teknik Ar-Ge yol haritasını çıkar", "rnd"),
        ("Hangi kütüphaneyi ekleyelim", "rnd"),
        ("https://github.com/bariscandasci/ankaras", "brief"),
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
    decision = heuristic_route("satış bütçesi")
    assert decision.route == "general"
    assert decision.reason == "ambiguous"


def test_llm_route_json_is_normalized():
    assert _parse_route('```json\n{"route": "finance"}\n```') == "finance"
    assert _parse_route("muhasebe") == "finance"
    assert _parse_route("ar-ge") == "rnd"
    assert _parse_route("emin değilim") is None


def test_gemini_client_uses_the_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    from config import get_chat_model, get_settings

    settings = get_settings()
    model = get_chat_model(settings)
    assert settings.model == "gemini-3.6-flash"
    assert model.model_name == "gemini-3.6-flash"
    assert model.use_responses_api is False
    assert model.openai_api_base == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_gemini_error_includes_status_and_message():
    from config import describe_llm_error

    class FakeError(Exception):
        status_code = 400
        body = [
            {
                "error": {
                    "code": 400,
                    "message": "Please pass a valid API key",
                    "status": "INVALID_ARGUMENT",
                }
            }
        ]

    detail = describe_llm_error(FakeError())
    assert "HTTP 400" in detail
    assert "Please pass a valid API key" in detail
    assert "INVALID_ARGUMENT" in detail


def test_gemini_payload_matches_the_compatible_tool_schema(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
    from langchain_core.messages import HumanMessage

    from agents.supervisor import DepartmentRoute
    from config import GEMINI_TOOL_EXTRAS, get_chat_model, get_settings
    from tools.finance_tools import FINANCE_TOOLS

    model = get_chat_model(get_settings())
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "add_expense", "arguments": "{}"},
                            "extra_content": {"google": {"thought_signature": "sig-1"}},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    message = model._create_chat_result(response).generations[0].message
    assert message.additional_kwargs[GEMINI_TOOL_EXTRAS]["call_1"]["google"]["thought_signature"] == "sig-1"

    binding = model.bind_tools(FINANCE_TOOLS[1:2], strict=True, parallel_tool_calls=False)
    payload = binding.bound._get_request_payload(
        [HumanMessage(content="personel"), message],
        **binding.kwargs,
    )
    function = payload["tools"][0]["function"]
    assert "strict" not in function
    assert "default" not in function["parameters"]["properties"]["category"]
    assert "parallel_tool_calls" not in payload
    replayed = payload["messages"][-1]["tool_calls"][0]["extra_content"]
    assert replayed["google"]["thought_signature"] == "sig-1"

    structured = model.with_structured_output(DepartmentRoute, method="json_schema", strict=True)
    step = structured.steps[0]
    structured_payload = step.bound._get_request_payload(
        [HumanMessage(content="personel listesi")],
        **step.kwargs,
    )
    assert "parallel_tool_calls" not in structured_payload
    assert "strict" not in structured_payload["tools"][0]["function"]
    assert "additionalProperties" not in str(structured_payload["tools"])


def test_tie_with_history_prefers_the_previous_department():
    decision = heuristic_route("satış bütçesi", previous="finance")
    assert decision.route == "finance"
    assert decision.reason == "follow_up"

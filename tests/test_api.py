"""HTTP arayüzü."""

from fastapi.testclient import TestClient

from memory.session import Orchestrator
from api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(Orchestrator()))


def test_health_reports_mock_mode_and_the_four_agents():
    with _client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_configured"] is False
    assert body["provider"] == "openai"
    assert [agent["id"] for agent in body["agents"]] == ["supervisor", "hr", "finance", "ops"]


def test_chat_returns_the_hr_report():
    with _client() as client:
        response = client.post("/chat", json={"message": "Personel listesini çıkar", "session_id": "demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["department"] == "hr"
    assert body["mode"] == "mock"
    assert "Ayşe Demir" in body["answer"]
    assert body["session_id"] == "demo"


def test_blank_message_is_rejected():
    with _client() as client:
        response = client.post("/chat", json={"message": "   "})
    assert response.status_code == 422


def test_session_continues_through_the_api():
    with _client() as client:
        first = client.post("/chat", json={"message": "Açık faturaları listele", "session_id": "api-1"})
        second = client.post("/chat", json={"message": "peki", "session_id": "api-1"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["department"] == "finance"
    assert second.json()["reason"] == "follow_up"

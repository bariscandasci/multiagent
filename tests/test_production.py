"""Canlı yayın, atomik yazma, yedek hız sınırı ve yönetici kimliği."""

import json
import threading

import pytest

from langchain_core.messages import AIMessage, HumanMessage

from agents.brief import brief_node
from agents.handoff import compact_handoff
from agents.runtime import prune_messages
from api.app import create_app
from config import get_fallback_rate_limiter, get_rate_limiter, reset_llm_runtime
from fastapi.testclient import TestClient
from memory.session import Orchestrator
from tools.json_store import json_lock, save_json_safe


def test_compact_handoff_keeps_numbers_and_caps_words():
    prose = " ".join(f"kelime{index}" for index in range(240))
    text = prose + "\nAylık sabit gider toplamı: 45.000 TL"
    summary = compact_handoff(text)
    body = summary.split("Sayısal veriler:")[0]
    assert len(body.split()) <= 203
    assert "45.000 TL" in summary
    assert "kelime239" not in summary

    pruned = prune_messages(
        [
            HumanMessage(content="Aylık sabit giderleri çıkar"),
            AIMessage(content=text, name="finance_agent"),
        ]
    )
    assert pruned[0].content == "Aylık sabit giderleri çıkar"
    assert "kelime239" not in pruned[1].content
    assert "45.000 TL" in pruned[1].content


def test_brief_forwards_a_summary_and_keeps_the_full_report(monkeypatch):
    seen: list[str] = []

    def fake(prompt, tools, messages, plan_calls, temperature):
        del tools, messages, plan_calls, temperature
        seen.append(prompt)
        return (("kelime " * 240) + "TAM RAPOR\nToplam: 45.000 TL", ["read_project"], "llm")

    monkeypatch.setattr("agents.brief._llm_section", fake)
    result = brief_node({"messages": [HumanMessage(content="incele")], "project_slug": "ornek", "trace": []})
    answer = result["messages"][0].content
    assert answer.count("TAM RAPOR") == 3
    assert seen[1].count("kelime") <= 200
    assert "45.000 TL" in seen[1]
    assert "Yönetici Özeti" in seen[1]
    assert "TAM RAPOR" not in seen[1]


def test_parallel_json_updates_stay_intact(tmp_path):
    path = tmp_path / "giderler.json"
    save_json_safe(path, {"n": 0})
    errors: list[BaseException] = []

    def bump() -> None:
        try:
            with json_lock(path):
                current = json.loads(path.read_text(encoding="utf-8"))
                current["n"] += 1
                save_json_safe(path, current)
        except BaseException as exc:
            errors.append(exc)

    workers = [threading.Thread(target=bump) for _ in range(12)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert errors == []
    assert json.loads(path.read_text(encoding="utf-8"))["n"] == 12
    assert list(tmp_path.glob("*.tmp")) == []


def test_fallback_limiter_is_separate_from_the_primary():
    reset_llm_runtime()
    primary = get_rate_limiter(4)
    fallback = get_fallback_rate_limiter(15)
    assert primary is not fallback
    assert primary.requests_per_second == 4 / 60
    assert fallback.requests_per_second == 15 / 60
    assert fallback.max_bucket_size == 1
    assert get_fallback_rate_limiter(15) is fallback


def test_admin_auth_is_off_until_both_secrets_exist(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    with TestClient(create_app(Orchestrator())) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 200


def test_health_is_public_while_admin_auth_is_on(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "yonetici")
    monkeypatch.setenv("ADMIN_PASSWORD", "gizli-sifre")
    with TestClient(create_app(Orchestrator())) as client:
        open_probe = client.get("/api/health")
        wrong = client.get("/api/health", auth=("yonetici", "yanlis"))
        protected = client.get("/")
    assert open_probe.status_code == 200
    assert open_probe.json()["status"] == "ok"
    assert open_probe.json()["version"] == "1.0.0"
    assert wrong.status_code == 200
    assert wrong.json()["status"] == "ok"
    assert wrong.json()["version"] == "1.0.0"
    assert protected.status_code == 401


def test_robots_txt_and_header_stay_present_when_admin_auth_is_on(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "yonetici")
    monkeypatch.setenv("ADMIN_PASSWORD", "gizli-sifre")
    with TestClient(create_app(Orchestrator())) as client:
        robots = client.get("/robots.txt")
        health = client.get("/api/health")
        blocked = client.get("/")
    assert robots.status_code == 200
    assert robots.text == "User-agent: *\nDisallow: /\n"
    assert robots.headers["x-robots-tag"] == "noindex, nofollow"
    assert health.headers["x-robots-tag"] == "noindex, nofollow"
    assert blocked.status_code == 401
    assert blocked.headers["x-robots-tag"] == "noindex, nofollow"


def test_listen_hosts_stay_on_loopback_unless_bind_ip_is_private():
    from deploy.bind import listen_hosts

    assert listen_hosts(None) == ["127.0.0.1"]
    assert listen_hosts("127.0.0.1") == ["127.0.0.1"]
    assert listen_hosts("100.64.0.8") == ["127.0.0.1", "100.64.0.8"]
    with pytest.raises(SystemExit):
        listen_hosts("0.0.0.0")
    with pytest.raises(SystemExit):
        listen_hosts("203.0.113.10")


def test_admin_auth_protects_the_ui_and_the_sync_chat(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "yonetici")
    monkeypatch.setenv("ADMIN_PASSWORD", "gizli-sifre")
    with TestClient(create_app(Orchestrator())) as client:
        blocked = client.get("/")
        wrong = client.get("/api/agents", auth=("yonetici", "yanlis"))
        page = client.get("/", auth=("yonetici", "gizli-sifre"))
        chat = client.post(
            "/api/chat",
            auth=("yonetici", "gizli-sifre"),
            json={"message": "Aylık sabit giderleri çıkar", "session_id": "auth-1"},
        )
    assert blocked.status_code == 401
    assert "Basic" in blocked.headers["www-authenticate"]
    assert wrong.status_code == 401
    assert page.status_code == 200
    assert "AI Command Center" in page.text
    assert chat.status_code == 200
    assert chat.json()["department"] == "finance"


def test_stream_publishes_the_running_agent_and_its_section():
    with TestClient(create_app(Orchestrator())) as client:
        response = client.post(
            "/api/chat/stream",
            json={"message": "Aylık sabit giderleri çıkar", "session_id": "stream-live"},
        )
    assert response.status_code == 200
    assert '"status": "running"' in response.text
    assert '"phase": "section"' in response.text
    assert '"phase": "done"' in response.text
    assert "45.000 TL" in response.text

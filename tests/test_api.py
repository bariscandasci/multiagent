"""HTTP arayüzü."""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.report import split_report
from main import resolve_ssl
from memory.session import Orchestrator
from tools.github_tools import save_project


def _client() -> TestClient:
    return TestClient(create_app(Orchestrator()))


def _record() -> dict:
    return {
        "company": "BCD TECHNOLOGIES",
        "owner": "bariscandasci",
        "repo": "ankaras",
        "slug": "bariscandasci__ankaras",
        "url": "https://github.com/bariscandasci/ankaras",
        "description": "Belediye hizmet masası",
        "default_branch": "main",
        "private": False,
        "language": "Python",
        "languages": ["Python"],
        "readme": "Ankara belediye taleplerini izler.",
        "tree": ["app.py"],
        "dependencies": {},
        "fetched_at": "2026-11-17T00:00:00+00:00",
    }


def test_health_reports_the_bcd_agents():
    with _client() as client:
        response = client.get("/api/health")
        missing = client.get("/health")
    assert missing.status_code == 404
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"
    assert body["llm_configured"] is False
    assert body["provider"] == "openai"
    assert [agent["id"] for agent in body["agents"]] == ["supervisor", "market", "finance", "rnd"]


def test_home_is_the_command_center():
    with _client() as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Çoklu Ajan Komuta Merkezi" in response.text
    assert "AI Command Center" in response.text
    assert "Ajanları Çalıştır" in response.text
    assert "Ajan Eğitimi" in response.text
    assert "Kurumsal Doküman" in response.text
    assert "/api/knowledge/upload" in response.text
    assert "PDF Teklif İndir" in response.text
    assert "Müşteri E-postası Oluştur" in response.text


def test_virtual_office_tab_is_on_the_home_page():
    with _client() as client:
        response = client.get("/")
    assert response.status_code == 200
    page = response.text
    assert 'id="nav-office"' in page
    assert 'id="view-office"' in page
    assert "Sanal Ofis" in page
    assert "Yönetim Odası" in page
    assert "Teknik Ar-Ge Lab" in page
    assert 'data-agent="market"' in page
    assert 'data-agent="finance"' in page
    assert "Maliyet hesaplanıyor..." in page
    assert "4 DEPARTMAN" in page
    assert "Ekibine bir görev ver..." in page
    assert "YÖNETİM" in page
    assert "FİNANS &amp; MUHASEBE" in page
    assert 'credentials: "same-origin"' in page
    assert "function apiFetch" in page
    assert "function generateId" in page
    assert "typeof crypto.randomUUID" in page
    assert "crypto.getRandomValues" in page


def test_chat_returns_the_finance_ledger():
    with _client() as client:
        response = client.post(
            "/api/chat",
            json={"message": "Aylık sabit giderleri çıkar", "session_id": "demo"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["department"] == "finance"
    assert body["mode"] == "mock"
    assert "BCD TECHNOLOGIES" in body["answer"]
    assert "45.000 TL" in body["answer"]
    assert "45.000 TL" in body["sections"]["finance"]
    assert body["session_id"] == "demo"


def test_chat_stream_emits_tools_then_the_report():
    with _client() as client:
        response = client.post(
            "/api/chat/stream",
            json={"message": "Aylık sabit giderleri çıkar", "session_id": "stream-1"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "Yönetici isteği ayırıyor" in response.text
    assert "get_monthly_expenses" in response.text
    assert '"phase": "done"' in response.text


def test_blank_message_is_rejected():
    with _client() as client:
        response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


def test_session_continues_through_the_api():
    with _client() as client:
        first = client.post("/api/chat", json={"message": "Aylık sabit giderleri çıkar", "session_id": "api-1"})
        second = client.post("/api/chat", json={"message": "peki", "session_id": "api-1"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["department"] == "finance"
    assert second.json()["reason"] == "follow_up"


def test_project_list_and_saved_analysis():
    save_project(_record())
    with _client() as client:
        listing = client.get("/api/projects")
        detail = client.get("/api/projects/bariscandasci__ankaras")
        missing = client.get("/api/projects/yok")
    assert listing.status_code == 200
    assert listing.json()[0]["repo"] == "ankaras"
    assert detail.status_code == 200
    body = detail.json()
    assert "Kamu ve yerel yönetimler" in body["sections"]["market"]
    assert "Ar-Ge yol haritası" in body["sections"]["rnd"]
    assert missing.status_code == 404


def test_expense_post_updates_the_ledger():
    with _client() as client:
        created = client.post(
            "/api/expenses",
            json={"name": "Harita API", "amount": 1200, "category": "teknoloji", "project": "ankaras"},
        )
        listing = client.get("/api/expenses")
        rejected = client.post("/api/expenses", json={"name": "Eksi", "amount": -5, "category": "sabit"})
    assert created.status_code == 200
    assert created.json()["message"].startswith("BCD TECHNOLOGIES")
    assert any(row["name"] == "Harita API" for row in listing.json()["project_costs"])
    assert rejected.status_code == 422


def test_report_splitter_keeps_the_four_panels():
    answer = "\n\n".join(
        [
            "BCD TECHNOLOGIES — Yönetici Raporu",
            "Proje kaydı: ornek",
            "## Pazar ve satış",
            "Kamu alıcısı.",
            "## Teknik Ar-Ge",
            "Yol haritası.",
            "## Maliyet ve kâr",
            "45.000 TL",
        ]
    )
    sections = split_report(answer, "brief")
    assert "Yönetici Raporu" in sections["executive"]
    assert sections["market"] == "Kamu alıcısı."
    assert sections["rnd"] == "Yol haritası."
    assert sections["finance"] == "45.000 TL"


def test_chat_trace_records_supervisor_and_finance():
    with _client() as client:
        response = client.post("/api/chat", json={"message": "Aylık sabit giderleri çıkar", "session_id": "trace-1"})
    assert response.status_code == 200
    steps = response.json()["trace"]
    assert [step["id"] for step in steps] == ["supervisor", "finance"]
    assert "get_monthly_expenses" in steps[-1]["tools"]
    assert steps[-1]["duration_ms"] >= 0


def test_expense_can_be_edited_and_removed():
    with _client() as client:
        patched = client.patch("/api/expenses/ofis", json={"amount": 1000, "name": "Ofis"})
        created = client.post(
            "/api/expenses",
            json={"name": "Harita API", "amount": 1000, "category": "teknoloji", "project": "ankaras"},
        )
        row = next(item for item in created.json()["project_costs"] if item["name"] == "Harita API")
        removed = client.delete(f"/api/expenses/{row['id']}")
        missing = client.delete("/api/expenses/yok")
    assert patched.status_code == 200
    assert patched.json()["fixed_monthly"][0]["name"] == "Ofis"
    assert patched.json()["fixed_total"] == 1000
    assert created.status_code == 200
    assert created.json()["monthly_total"] == 2000
    assert created.json()["target_profit"] == 538
    assert removed.status_code == 200
    assert removed.json()["project_costs"] == []
    assert missing.status_code == 404


def test_agent_directives_and_memory_are_saved():
    with _client() as client:
        current = client.get("/api/agents/config")
        agents = current.json()["agents"]
        for agent in agents:
            if agent["id"] == "market":
                agent["directive"] = "HEDEF-SEKTOR-KAMU"
                agent["temperature"] = 0.4
        saved = client.post("/api/agents/config", json={"agents": agents})
        noted = client.post("/api/memory", json={"text": "Teknik standart: pytest zorunlu"})
        from agents.context import compose_prompt
        from agents.supervisor import routing_prompt

        prompt = compose_prompt("market", "varsayilan")
        routed = routing_prompt()
        note_id = noted.json()["notes"][0]["id"]
        cleared = client.delete(f"/api/memory/{note_id}")
        missing = client.delete("/api/memory/yok")
        too_hot = client.post(
            "/api/agents/config",
            json={"agents": [{**agent, "temperature": 3} for agent in agents]},
        )
    assert current.status_code == 200
    assert [agent["id"] for agent in agents] == ["supervisor", "market", "rnd", "finance"]
    market = next(agent for agent in saved.json()["agents"] if agent["id"] == "market")
    assert market["directive"] == "HEDEF-SEKTOR-KAMU"
    assert market["temperature"] == 0.4
    assert "HEDEF-SEKTOR-KAMU" in prompt
    assert "pytest zorunlu" in prompt
    assert "varsayilan" not in prompt
    assert "pytest zorunlu" in routed
    assert cleared.status_code == 200
    assert cleared.json()["notes"] == []
    assert missing.status_code == 404
    assert too_hot.status_code == 422


def test_market_node_reads_the_saved_directive(monkeypatch):
    seen = {}

    def fake(agent_id, fallback, extra="", query=""):
        seen["id"] = agent_id
        seen["extra"] = extra
        seen["query"] = query
        return fallback

    monkeypatch.setattr("agents.market_agent.compose_prompt", fake)
    from langchain_core.messages import HumanMessage

    from agents.market_agent import market_node

    market_node({"messages": [HumanMessage(content="hangi sektore satilir")], "trace": []})
    assert seen["id"] == "market"


def test_pdf_export_is_a_turkish_proposal():
    with _client() as client:
        response = client.post(
            "/api/export/pdf",
            json={
                "project_name": "İstanbul Belediyesi",
                "sections": {
                    "executive": "BCD TECHNOLOGIES — Yönetici özeti\nMüşteri değeri yüksek.",
                    "market": "Sektör: kamu ve yerel yönetimler.",
                    "rnd": "Ar-Ge yol haritası hazır.",
                    "finance": "Sabit gider toplamı 45.000 TL.",
                },
            },
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    disposition = response.headers["content-disposition"]
    assert "bcd-istanbul-belediyesi.pdf" in disposition
    payload = response.content
    assert payload.startswith(b"%PDF")
    assert b"BCD TECHNOLOGIES" in payload
    assert b"DejaVu" in payload
    # Alt küme yazı tipinin Unicode eşlemesi kullanılan Türkçe harfleri taşır.
    assert b"0130" in payload
    assert b"015F" in payload
    assert len(payload) > 5000


def test_draft_email_uses_the_saved_analysis_offline():
    with _client() as client:
        response = client.post(
            "/api/agents/draft-email",
            json={
                "project_name": "ankaras",
                "customer_profile": "belediye bilgi işlem müdürlüğü",
                "sections": {"market": "Kamu alıcısına satış stratejisi."},
            },
        )
        blank = client.post("/api/agents/draft-email", json={"customer_profile": " "})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mock"
    assert body["model"] == ""
    assert "ankaras" in body["subject"]
    assert "belediye bilgi işlem müdürlüğü" in body["body"]
    assert "BCD TECHNOLOGIES" in body["body"]
    assert "Kamu alıcısına satış stratejisi." in body["body"]
    assert blank.status_code == 422


def test_draft_email_prefers_the_configured_model(monkeypatch):
    class _Model:
        def invoke(self, messages):
            from langchain_core.messages import AIMessage

            return AIMessage(content='{"subject":"Ankara demosu","body":"Sayın ekip,\\n\\nBCD TECHNOLOGIES demo talep eder."}')

    class _Settings:
        configured = True
        model = "gemini-3.8-flash"

    monkeypatch.setattr("api.email_draft.bind_agent_model", lambda *args, **kwargs: _Model())
    monkeypatch.setattr("api.email_draft.get_settings", lambda: _Settings())
    with _client() as client:
        response = client.post(
            "/api/agents/draft-email",
            json={"project_name": "ankaras", "customer_profile": "belediye bilgi işlem", "sections": {"market": "Kamu"}},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "llm"
    assert body["model"] == "gemini-3.8-flash"
    assert body["subject"] == "Ankara demosu"
    assert "BCD TECHNOLOGIES" in body["body"]


def test_ssl_flags_require_both_files():
    assert resolve_ssl(None, None) is None
    assert resolve_ssl("key.pem", "cert.pem") == ("key.pem", "cert.pem")
    with pytest.raises(ValueError):
        resolve_ssl("key.pem", None)

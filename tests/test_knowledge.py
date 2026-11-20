"""Kurumsal bilgi bankası yükleme, silme ve ajan istemine bağlama."""

from fpdf import FPDF
from fastapi.testclient import TestClient

from api.app import create_app
from agents.context import compose_prompt
from memory.session import Orchestrator
import tools.knowledge as knowledge
from tools.knowledge import reference_block


def _client() -> TestClient:
    return TestClient(create_app(Orchestrator()))


def _pdf(text: str) -> bytes:
    document = FPDF()
    document.add_page()
    document.set_font("Helvetica", size=12)
    document.multi_cell(0, 8, text)
    payload = document.output()
    return bytes(payload)


def test_markdown_upload_is_retrieved_only_for_its_department():
    with _client() as client:
        uploaded = client.post(
            "/api/knowledge/upload",
            files={"file": ("fiyat-kurali.md", "Iskonto tavani yuzde onikidir. Bunun ustune cikilmaz.".encode(), "text/markdown")},
            data={"department": "finance"},
        )
        shared = client.post(
            "/api/knowledge/upload",
            files={"file": ("kamu.txt", "Kamu ihalelerinde teslim suresi alti haftadir.".encode(), "text/plain")},
            data={"department": "all"},
        )
        listed = client.get("/api/knowledge")
        rejected = client.post(
            "/api/knowledge/upload",
            files={"file": ("notlar.docx", b"gizli", "application/octet-stream")},
            data={"department": "market"},
        )
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["department"] == "finance"
    assert body["chunk_count"] >= 1
    assert "Iskonto" in body["summary"]
    assert shared.status_code == 200
    assert listed.status_code == 200
    assert len(listed.json()["documents"]) == 2
    assert rejected.status_code == 422
    finance_prompt = compose_prompt("finance", "varsayilan", query="iskonto tavani nedir")
    market_prompt = compose_prompt("market", "varsayilan", query="iskonto tavani nedir")
    shared_prompt = compose_prompt("market", "varsayilan", query="kamu ihale teslim suresi")
    assert "KURUMSAL REFERANS DOKÜMANLARI" in finance_prompt
    assert "yuzde onikidir" in finance_prompt
    assert "uydurma" in finance_prompt
    assert "yuzde onikidir" not in market_prompt
    assert "alti haftadir" in shared_prompt
    assert "yuzde onikidir" not in shared_prompt
    stored = knowledge.INDEX_PATH.read_text(encoding="utf-8")
    assert "chunks" in stored


def test_pdf_upload_reaches_the_rnd_prompt_and_can_be_deleted():
    payload = _pdf("BAKIM STANDARDI 48 SAAT icinde mudahale edilir.")
    with _client() as client:
        uploaded = client.post(
            "/api/knowledge/upload",
            files={"file": ("bakim-standardi.pdf", payload, "application/pdf")},
            data={"department": "rnd"},
        )
        assert uploaded.status_code == 200
        doc_id = uploaded.json()["id"]
        prompt = reference_block("rnd", "bakim standardi mudahale")
        assert "BAKIM STANDARDI" in prompt
        assert "uydurma" in prompt
        removed = client.delete(f"/api/knowledge/{doc_id}")
        missing = client.delete(f"/api/knowledge/{doc_id}")
    assert "BAKIM STANDARDI" in removed.text or removed.status_code == 200
    assert removed.json()["documents"] == []
    assert missing.status_code == 404
    assert reference_block("rnd", "bakim standardi") == ""


def test_knowledge_upload_requires_admin_when_auth_is_on(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "yonetici")
    monkeypatch.setenv("ADMIN_PASSWORD", "gizli-sifre")
    with _client() as client:
        blocked = client.post(
            "/api/knowledge/upload",
            files={"file": ("kural.txt", b"Standart metin.", "text/plain")},
            data={"department": "manager"},
        )
        opened = client.post(
            "/api/knowledge/upload",
            files={"file": ("kural.txt", b"Standart metin.", "text/plain")},
            data={"department": "manager"},
            auth=("yonetici", "gizli-sifre"),
        )
    assert blocked.status_code == 401
    assert opened.status_code == 200
    assert "Standart metin" in compose_prompt("supervisor", "varsayilan", query="standart metin")

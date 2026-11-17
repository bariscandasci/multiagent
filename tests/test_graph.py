"""Grafik ve oturum belleği."""

from langchain_core.messages import HumanMessage

from agents.graph import build_graph
from memory.session import Orchestrator
from tools.github_tools import format_project, save_project


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
        "dependencies": {"requirements.txt": "fastapi\n"},
        "fetched_at": "2026-11-17T00:00:00+00:00",
    }


def test_graph_registers_every_department():
    graph = build_graph()
    names = set(graph.get_graph().nodes)
    assert {"supervisor", "market_agent", "finance_agent", "rnd_agent", "brief"} <= names


def test_single_turn_reads_the_finance_ledger():
    graph = build_graph()
    result = graph.invoke({"messages": [HumanMessage(content="Aylık sabit giderleri çıkar")]})
    assert result["department"] == "finance"
    assert "get_monthly_expenses" in result["tools_used"]
    assert "BCD TECHNOLOGIES" in result["messages"][-1].content
    assert "45.000 TL" in result["messages"][-1].content


def test_session_memory_keeps_the_department_and_isolates_threads():
    orchestrator = Orchestrator()
    first = orchestrator.ask("Aylık sabit giderleri çıkar", "s1")
    follow = orchestrator.ask("peki", "s1")
    other = orchestrator.ask("peki", "s2")

    assert first["department"] == "finance"
    assert "get_monthly_expenses" in first["tools_used"]
    assert "Ofis ve altyapı" in first["answer"]
    assert follow["department"] == "finance"
    assert follow["reason"] == "follow_up"
    assert other["route"] == "general"
    assert other["department"] == "supervisor"


def test_market_and_rnd_reports_use_the_saved_project():
    save_project(_record())
    orchestrator = Orchestrator()
    market = orchestrator.ask("Bu projeyi hangi sektörlere satabiliriz", "m")
    rnd = orchestrator.ask("Teknik Ar-Ge yol haritasını çıkar", "r")

    assert market["department"] == "market"
    assert "read_project" in market["tools_used"]
    assert "Kamu ve yerel yönetimler" in market["answer"]
    assert rnd["department"] == "rnd"
    assert "read_project" in rnd["tools_used"]
    assert "Ar-Ge yol haritası" in rnd["answer"]


def test_github_link_coordinates_one_executive_report(monkeypatch):
    class Stub:
        def invoke(self, payload):
            del payload
            record = _record()
            save_project(record)
            return format_project(record)

    monkeypatch.setattr("agents.supervisor.fetch_github_repo", Stub())
    orchestrator = Orchestrator()
    result = orchestrator.ask("https://github.com/bariscandasci/ankaras", "repo")

    assert result["department"] == "brief"
    assert result["reason"] == "github"
    assert "fetch_github_repo" in result["tools_used"]
    assert "read_project" in result["tools_used"]
    assert "get_monthly_expenses" in result["tools_used"]
    assert "simulate_project_budget" in result["tools_used"]
    assert "BCD TECHNOLOGIES — Yönetici Raporu" in result["answer"]
    assert "Kamu ve yerel yönetimler" in result["answer"]
    assert "Ar-Ge yol haritası" in result["answer"]
    assert "45.000 TL" in result["answer"]

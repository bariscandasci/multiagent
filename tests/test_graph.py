"""Grafik ve oturum belleği."""

from langchain_core.messages import HumanMessage

from agents.graph import build_graph
from memory.session import Orchestrator


def test_graph_registers_every_department():
    graph = build_graph()
    names = set(graph.get_graph().nodes)
    assert {"supervisor", "hr_agent", "finance_agent", "ops_agent"} <= names


def test_single_turn_routes_without_a_checkpointer():
    graph = build_graph()
    result = graph.invoke({"messages": [HumanMessage(content="Personel listesini çıkar")]})
    assert result["department"] == "hr"
    assert "list_employees" in result["tools_used"]
    assert "Ayşe Demir" in result["messages"][-1].content


def test_session_memory_keeps_the_department_and_isolates_threads():
    orchestrator = Orchestrator()
    first = orchestrator.ask("Açık faturaları listele", "s1")
    follow = orchestrator.ask("peki", "s1")
    other = orchestrator.ask("peki", "s2")

    assert first["department"] == "finance"
    assert "list_invoices" in first["tools_used"]
    assert "Atlas Lojistik" in first["answer"]
    assert follow["department"] == "finance"
    assert follow["reason"] == "follow_up"
    assert other["route"] == "general"
    assert other["department"] == "supervisor"


def test_finance_and_ops_reports_use_their_tools():
    orchestrator = Orchestrator()
    finance = orchestrator.ask("Son çeyrek gelir gider özeti ve geciken faturalar", "f")
    ops = orchestrator.ask("Sunucu durumunu kontrol et ve teknik iş planı çıkar", "o")

    assert finance["department"] == "finance"
    assert "income_expense_summary" in finance["tools_used"]
    assert "list_invoices" in finance["tools_used"]
    assert "3.520.000 TL" in finance["answer"]
    assert "Bulut Host" in finance["answer"]

    assert ops["department"] == "ops"
    assert "server_status" in ops["tools_used"]
    assert "plan_technical_tasks" in ops["tools_used"]
    assert "worker-01" in ops["answer"]
    assert "kapalı" in ops["answer"]

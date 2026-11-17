"""Teknik ve operasyon ajanı."""

from __future__ import annotations

from agents.runtime import run_department
from agents.state import AgentState
from tools.common import COMPANY, contains_term, dedupe_calls, fold
from tools.ops_tools import OPS_TOOLS, known_server

SYSTEM_PROMPT = f"""Sen {COMPANY} içindeki Teknik ve Operasyon ajanısın.
Sunucu durumu, olay kaydı ve teknik iş planı sorularını araçlarla yanıtla.
Uydurma metrik yazma. Yanıtı Türkçe ve uygulanabilir bir özet olarak yaz.
Veriler örnek şirket veri setindendir; raporda bunu kısaca belirt."""


def plan_ops_calls(text: str) -> list[tuple[str, dict]]:
    folded = fold(text)
    server = known_server(folded)
    calls: list[tuple[str, dict]] = []
    incident_terms = ("incident", "kesinti", "ariza", "olay")
    if any(contains_term(folded, term) for term in incident_terms) or "inc-" in folded:
        show_all = any(term in folded for term in ("cozul", "kapanan", "tum olay", "hepsi"))
        calls.append(("list_incidents", {"open_only": not show_all}))
    if any(term in folded for term in ("bakim", "teknik gorev", "is plani", "yapilacak")):
        calls.append(("plan_technical_tasks", {"focus": server}))
    wants_status = bool(server) or any(
        contains_term(folded, term)
        for term in ("sunucu", "cpu", "bellek", "disk", "uptime", "heartbeat", "servis")
    )
    if "sistem durum" in folded:
        wants_status = True
    if wants_status or not calls:
        calls.append(("server_status", {"name": server}))
    return dedupe_calls(calls)


def ops_node(state: AgentState) -> dict:
    return run_department(
        state,
        department="ops",
        agent_name="ops_agent",
        title=f"Teknik & Operasyon Ajanı — {COMPANY}",
        system_prompt=SYSTEM_PROMPT,
        tools=OPS_TOOLS,
        plan_calls=plan_ops_calls,
    )

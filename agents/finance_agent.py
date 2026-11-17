"""Muhasebe ve finans ajanı."""

from __future__ import annotations

from agents.context import agent_temperature, compose_prompt
from agents.runtime import run_department
from agents.state import AgentState
from tools.common import COMPANY, contains_term, dedupe_calls, fold
from tools.finance_tools import FINANCE_TOOLS, parse_amount

SYSTEM_PROMPT = f"""Sen {COMPANY} içindeki Muhasebe ve Finans ajanısın.
Tutarları yalnızca get_monthly_expenses, add_expense ve simulate_project_budget sonuçlarından yaz.
Aylık sabit gideri, yeni bir iş veya ek teknoloji maliyetini, önerilen fiyatı ve net kârı Türkçe özetle.
Deftere yazılmayan tutarı gerçekleşmiş gider gibi gösterme."""


def plan_finance_calls(text: str) -> list[tuple[str, dict]]:
    folded = fold(text)
    calls: list[tuple[str, dict]] = []
    amount = parse_amount(text)
    wants_add = any(contains_term(folded, term) for term in ("ekle", "kaydet", "yeni gider", "maliyet ekle"))
    if wants_add and amount is not None:
        project = ""
        if "proje" in folded:
            project = "yeni proje"
        calls.append(("add_expense", {"name": "Ek gider", "amount": amount, "category": "teknoloji", "project": project}))
    wants_sim = any(
        contains_term(folded, term)
        for term in ("simul", "butce", "karlilik", "fiyat", "teklif", "net kar")
    )
    if wants_sim or contains_term(folded, "kar"):
        calls.append(
            (
                "simulate_project_budget",
                {
                    "project": "yeni iş",
                    "monthly_price": amount or 0,
                    "extra_monthly_cost": 0,
                    "note": "",
                },
            )
        )
    if any(contains_term(folded, term) for term in ("gider", "maliyet", "muhasebe", "sabit")) or not calls:
        calls.insert(0, ("get_monthly_expenses", {}))
    return dedupe_calls(calls)


def finance_node(state: AgentState) -> dict:
    slug = str(state.get("project_slug") or "")
    extra = f"Simülasyonu {slug} projesi için çalıştır." if slug else ""
    return run_department(
        state,
        department="finance",
        agent_name="finance_agent",
        title=f"Muhasebe & Finans — {COMPANY}",
        pipeline_label="Muhasebe",
        system_prompt=compose_prompt("finance", SYSTEM_PROMPT, extra),
        tools=FINANCE_TOOLS,
        plan_calls=plan_finance_calls,
        temperature=agent_temperature("finance"),
    )

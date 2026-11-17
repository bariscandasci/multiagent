"""Finans ve muhasebe ajanı."""

from __future__ import annotations

from agents.runtime import run_department
from agents.state import AgentState
from tools.common import COMPANY, contains_term, dedupe_calls, detect_department, fold
from tools.finance_tools import FINANCE_TOOLS

SYSTEM_PROMPT = f"""Sen {COMPANY} içindeki Finans ve Muhasebe ajanısın.
Gelir-gider, fatura ve bütçe sorularını araçlarla yanıtla. Araçların vermediği tutarı yazma.
Yanıtı Türkçe, kısa bir finansal özet olarak yaz.
Veriler örnek şirket veri setindendir; raporda bunu kısaca belirt."""


def plan_finance_calls(text: str) -> list[tuple[str, dict]]:
    folded = fold(text)
    calls: list[tuple[str, dict]] = []
    if any(contains_term(folded, term) for term in ("fatura", "tahsilat", "vade", "alacak", "borc")) or "f-" in folded:
        status = ""
        if "gecik" in folded:
            status = "overdue"
        elif any(contains_term(folded, term) for term in ("odendi", "odenen", "kapali")):
            status = "paid"
        elif any(contains_term(folded, term) for term in ("acik", "odenmemis", "bekleyen")):
            status = "open"
        calls.append(("list_invoices", {"status": status}))
    if contains_term(folded, "butce") or contains_term(folded, "maliyet"):
        calls.append(("budget_summary", {"department": detect_department(text)}))
    wants_pnl = (
        any(
            contains_term(folded, term)
            for term in ("gelir", "gider", "nakit", "bilanco", "karlilik", "kar", "zarar")
        )
        or "ozet" in folded
    )
    if wants_pnl or not calls:
        period = "quarter"
        if any(term in folded for term in ("bu ay", "aylik", "bu ayki")):
            period = "month"
        elif any(term in folded for term in ("yillik", "bu yil", "alti ay", "6 ay")):
            period = "year"
        calls.append(("income_expense_summary", {"period": period}))
    return dedupe_calls(calls)


def finance_node(state: AgentState) -> dict:
    return run_department(
        state,
        department="finance",
        agent_name="finance_agent",
        title=f"Finans & Muhasebe Ajanı — {COMPANY}",
        system_prompt=SYSTEM_PROMPT,
        tools=FINANCE_TOOLS,
        plan_calls=plan_finance_calls,
    )

"""İK ve veri ajanı."""

from __future__ import annotations

from agents.runtime import run_department
from agents.state import AgentState
from tools.common import (
    COMPANY,
    contains_term,
    dedupe_calls,
    detect_department,
    fold,
    mentions_record,
)
from tools.hr_tools import CANDIDATES, EMPLOYEES, HR_TOOLS

SYSTEM_PROMPT = f"""Sen {COMPANY} içindeki İK ve Veri ajanısın.
Personel ve aday sorularını araçlarla yanıtla. Sayı, ad ve tarih uydurma.
Yanıtı Türkçe, kısa bir rapor olarak yaz. Selamlama ekleme.
Veriler örnek şirket veri setindendir; raporda bunu kısaca belirt."""


def plan_hr_calls(text: str) -> list[tuple[str, dict]]:
    folded = fold(text)
    calls: list[tuple[str, dict]] = []
    for person in EMPLOYEES:
        if mentions_record(folded, name=str(person["name"]), record_id=str(person["id"])):
            calls.append(("get_employee", {"query": str(person["id"])}))
    for candidate in CANDIDATES:
        if mentions_record(folded, name=candidate["name"], record_id=candidate["id"]):
            calls.append(("list_candidates", {"name": candidate["name"]}))
    if any(contains_term(folded, term) for term in ("aday", "mulakat", "basvuru", "teklif", "ise alim")):
        status = ""
        if contains_term(folded, "mulakat"):
            status = "mülakat"
        elif contains_term(folded, "teklif"):
            status = "teklif"
        calls.append(("list_candidates", {"status": status}))
    wants_people = any(
        contains_term(folded, term)
        for term in ("personel", "calisan", "kadro", "liste", "ekip", "bordro", "izin", "maas", "ucret")
    )
    if wants_people or not calls:
        calls.append(("list_employees", {"department": detect_department(text)}))
    return dedupe_calls(calls)


def hr_node(state: AgentState) -> dict:
    return run_department(
        state,
        department="hr",
        agent_name="hr_agent",
        title=f"İK & Veri Ajanı — {COMPANY}",
        system_prompt=SYSTEM_PROMPT,
        tools=HR_TOOLS,
        plan_calls=plan_hr_calls,
    )

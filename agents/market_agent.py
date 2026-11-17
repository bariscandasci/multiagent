"""Operasyon ve pazar geliştirme ajanı."""

from __future__ import annotations

from agents.context import agent_temperature, compose_prompt
from agents.runtime import last_user_text, run_department
from agents.state import AgentState
from tools.analysis import build_market_section
from tools.common import COMPANY, DISCLAIMER
from tools.github_tools import GITHUB_TOOLS

SYSTEM_PROMPT = f"""Sen {COMPANY} içindeki Operasyon ve Pazar Geliştirme ajanısın.
Projeyi fetch_github_repo veya read_project ile oku. Dosyada olmayan müşteri, sektör veya fiyat uydurma.
Hangi sektörlere, hangi ölçekteki firmalara ve hangi karar vericilere satılabileceğini yaz.
Değer önerisini ve üç adımlık satış stratejisini {COMPANY} adına, Türkçe ve kısa tut."""


def plan_market_calls(text: str) -> list[tuple[str, dict]]:
    return [("read_project", {"query": text})]


def market_node(state: AgentState) -> dict:
    slug = str(state.get("project_slug") or "")
    query = slug or last_user_text(list(state.get("messages") or []))

    def _finalize(answer: str, used: list[str]) -> str:
        del answer, used
        return f"{build_market_section(query)}\n\n{DISCLAIMER}"

    extra = f"İncelenen kayıt: {slug}. Önce read_project kullan." if slug else ""
    return run_department(
        state,
        department="market",
        agent_name="market_agent",
        title=f"Operasyon & Pazar Geliştirme — {COMPANY}",
        pipeline_label="Operasyon & Pazar",
        system_prompt=compose_prompt("market", SYSTEM_PROMPT, extra),
        tools=GITHUB_TOOLS,
        plan_calls=plan_market_calls,
        finalize=_finalize,
        temperature=agent_temperature("market"),
    )

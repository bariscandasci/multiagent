"""Teknik ve Ar-Ge ajanı."""

from __future__ import annotations

from agents.context import agent_temperature, compose_prompt
from agents.runtime import last_user_text, run_department
from agents.state import AgentState
from tools.analysis import build_rnd_section
from tools.common import COMPANY, DISCLAIMER
from tools.github_tools import GITHUB_TOOLS

SYSTEM_PROMPT = f"""Sen {COMPANY} içindeki Teknik ve Ar-Ge ajanısın.
Depodaki dosya ağacını ve bağımlılık dosyalarını read_project ile oku. Repoda olmayan kütüphane sürümü veya metrik yazma.
Projeyi rakiplerinden ayıracak özelliği, eklenebilecek güncel kütüphaneleri, yapay zeka entegrasyonunu ve adım adım Ar-Ge yol haritasını Türkçe yaz."""


def plan_rnd_calls(text: str) -> list[tuple[str, dict]]:
    return [("read_project", {"query": text})]


def rnd_node(state: AgentState) -> dict:
    slug = str(state.get("project_slug") or "")
    query = slug or last_user_text(list(state.get("messages") or []))

    def _finalize(answer: str, used: list[str]) -> str:
        del answer, used
        return f"{build_rnd_section(query)}\n\n{DISCLAIMER}"

    extra = f"İncelenen kayıt: {slug}." if slug else ""
    return run_department(
        state,
        department="rnd",
        agent_name="rnd_agent",
        title=f"Teknik & Ar-Ge — {COMPANY}",
        pipeline_label="Teknik Ar-Ge",
        system_prompt=compose_prompt("rnd", SYSTEM_PROMPT, extra),
        tools=GITHUB_TOOLS,
        plan_calls=plan_rnd_calls,
        finalize=_finalize,
        temperature=agent_temperature("rnd"),
    )

"""GitHub deposu için üç ajanın tek yönetici raporuna bağlanması."""

from __future__ import annotations

import logging
import time

from langchain_core.messages import AIMessage

from agents.context import agent_temperature, compose_prompt
from agents.finance_agent import SYSTEM_PROMPT as FINANCE_PROMPT
from agents.finance_agent import plan_finance_calls
from agents.market_agent import SYSTEM_PROMPT as MARKET_PROMPT
from agents.market_agent import plan_market_calls
from agents.handoff import compact_handoff
from agents.progress import announce, observe, publish_section
from agents.rnd_agent import SYSTEM_PROMPT as RND_PROMPT
from agents.rnd_agent import plan_rnd_calls
from agents.runtime import llm_answer, render_mock
from agents.state import AgentState
from config import describe_llm_error, get_settings
from tools.analysis import build_market_section, build_rnd_section
from tools.common import COMPANY, DISCLAIMER
from tools.finance_tools import FINANCE_TOOLS, get_monthly_expenses, simulate_project_budget
from tools.github_tools import GITHUB_TOOLS

logger = logging.getLogger(__name__)


def _llm_section(
    prompt: str,
    tools: list,
    messages: list,
    plan_calls,
    temperature: float | None,
) -> tuple[str, list[str], str]:
    settings = get_settings()
    if settings.configured:
        try:
            answer, used = llm_answer(settings, prompt, tools, messages, temperature)
        except Exception as exc:
            logger.warning("LLM bölümü başarısız, kayıtlara düşüldü: %s", describe_llm_error(exc))
        else:
            if used and answer.strip():
                return answer, used, "llm"
    answer, used = render_mock(COMPANY, messages, tools, plan_calls)
    return answer, used, "mock"


def _offline_finance(slug: str) -> tuple[str, list[str]]:
    project = slug.replace("__", "/") if slug else "yeni iş"
    expenses = str(get_monthly_expenses.invoke({}))
    budget = str(
        simulate_project_budget.invoke(
            {
                "project": project,
                "monthly_price": 0,
                "extra_monthly_cost": 0,
                "note": "depo incelemesi",
            }
        )
    )
    return f"{expenses}\n\n{budget}", ["get_monthly_expenses", "simulate_project_budget"]


def _with_handoff(base: str, handoff: str) -> str:
    if not handoff.strip():
        return base
    return (
        base
        + "\n\nÖnceki ajanlardan yönetici özeti. Tam raporu yeniden üretme; yalnız bu özeti ve sayıları kullan.\n"
        + handoff
    )


def brief_node(state: AgentState) -> dict:
    messages = list(state.get("messages") or [])
    slug = str(state.get("project_slug") or "")
    focus = f"Kayıt slug: {slug}. Önce read_project ile bu kaydı oku." if slug else ""
    carried: list[str] = []
    market_started = time.perf_counter()
    announce("market", "Operasyon & Pazar")
    market_text, market_tools, market_mode = _llm_section(
        compose_prompt("market", MARKET_PROMPT, _with_handoff(focus, "")),
        GITHUB_TOOLS,
        messages,
        plan_market_calls,
        agent_temperature("market"),
    )
    if market_mode == "mock":
        market_text = build_market_section(slug)
        market_tools = ["read_project"]
    publish_section("market", market_text)
    market_step = observe("market", "Operasyon & Pazar", market_tools, market_started)
    carried.append(market_text)
    rnd_started = time.perf_counter()
    announce("rnd", "Teknik Ar-Ge")
    rnd_text, rnd_tools, rnd_mode = _llm_section(
        compose_prompt("rnd", RND_PROMPT, _with_handoff(focus, compact_handoff("\n\n".join(carried)))),
        GITHUB_TOOLS,
        messages,
        plan_rnd_calls,
        agent_temperature("rnd"),
    )
    if rnd_mode == "mock":
        rnd_text = build_rnd_section(slug)
        rnd_tools = ["read_project"]
    publish_section("rnd", rnd_text)
    rnd_step = observe("rnd", "Teknik Ar-Ge", rnd_tools, rnd_started)
    carried.append(rnd_text)
    finance_focus = f"Simülasyonu {slug} için çalıştır." if slug else ""
    finance_started = time.perf_counter()
    announce("finance", "Muhasebe")
    finance_text, finance_tools, finance_mode = _llm_section(
        compose_prompt(
            "finance",
            FINANCE_PROMPT,
            _with_handoff(finance_focus, compact_handoff("\n\n".join(carried))),
        ),
        FINANCE_TOOLS,
        messages,
        plan_finance_calls,
        agent_temperature("finance"),
    )
    if finance_mode == "mock":
        finance_text, finance_tools = _offline_finance(slug)
    publish_section("finance", finance_text)
    finance_step = observe("finance", "Muhasebe", finance_tools, finance_started)
    modes = {market_mode, rnd_mode, finance_mode}
    report = "\n\n".join(
        [
            f"{COMPANY} — Yönetici Raporu",
            f"Proje kaydı: {slug or 'son kayıt'}",
            "## Pazar ve satış",
            market_text,
            "## Teknik Ar-Ge",
            rnd_text,
            "## Maliyet ve kâr",
            finance_text,
            DISCLAIMER,
        ]
    )
    tools = ["fetch_github_repo", *market_tools, *rnd_tools, *finance_tools]
    prior = [item for item in (state.get("trace") or []) if isinstance(item, dict)]
    return {
        "messages": [AIMessage(content=report, name="supervisor")],
        "department": "brief",
        "route": "brief",
        "mode": "llm" if modes == {"llm"} else "mock",
        "tools_used": tools,
        "project_slug": slug,
        "trace": prior + [market_step, rnd_step, finance_step],
    }

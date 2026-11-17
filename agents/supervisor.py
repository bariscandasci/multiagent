"""İsteği departman ajanına veya bütünleşik rapora ayıran yönetici."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.catalog import AGENTS
from agents.context import agent_temperature, compose_prompt
from agents.progress import announce, observe
from agents.runtime import last_user_text
from agents.state import AgentState
from config import bind_agent_model, describe_llm_error, get_settings
from tools.common import contains_term, fold
from tools.github_tools import fetch_github_repo, parse_repo_url

logger = logging.getLogger(__name__)

DEPARTMENTS = {"market", "finance", "rnd", "brief"}

MARKET_TERMS = (
    "pazar",
    "musteri",
    "sektor",
    "satis",
    "deger oner",
    "karar verici",
    "olcek",
)
FINANCE_TERMS = (
    "gider",
    "maliyet",
    "butce",
    "muhasebe",
    "fiyat",
    "karlilik",
    "net kar",
    "tahsilat",
    "finans",
)
FINANCE_EXACT = ("kar",)
RND_TERMS = (
    "ar-ge",
    "yol harita",
    "kutuphane",
    "teknik",
    "ozellik",
    "rakip",
    "entegrasyon",
    "kod",
    "mimari",
)
BRIEF_TERMS = ("butunlesik", "yonetici raporu", "uc uzman", "hepsini cikar")
SMALLTALK = (
    "merhaba",
    "selam",
    "hello",
    "hey",
    "gunaydin",
    "iyi gunler",
    "tesekkur",
    "sag ol",
    "hosca kal",
    "kimsin",
    "neler yapabilir",
    "ne yapabilir",
    "yardim",
    "help",
)


@dataclass(frozen=True)
class RouteDecision:
    route: str
    reason: str
    mode: str


class DepartmentRoute(BaseModel):
    """İsteğin gideceği tek akış."""

    route: str = Field(description="Yalnızca market, finance, rnd, brief veya general.")


def _score_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if contains_term(text, term))


def _is_smalltalk(text: str) -> bool:
    return any(contains_term(text, term) for term in SMALLTALK)


def extract_github_url(text: str) -> str:
    match = re.search(r"https?://github\.com/[\w.-]+/[\w.-]+", text or "", flags=re.IGNORECASE)
    if match:
        return match.group(0).rstrip(").,")
    stripped = (text or "").strip()
    if stripped and " " not in stripped and parse_repo_url(stripped):
        return stripped
    return ""


def heuristic_route(query: str, previous: str = "") -> RouteDecision:
    """Anahtarsız yönlendirme. Testler bu fonksiyonu sabitler."""
    folded = fold(query)
    if not folded.strip():
        return RouteDecision("general", "empty", "mock")
    if extract_github_url(query) or _score_terms(folded, BRIEF_TERMS):
        return RouteDecision("brief", "github" if extract_github_url(query) else "keyword", "mock")

    scores = {
        "market": _score_terms(folded, MARKET_TERMS),
        "finance": _score_terms(folded, FINANCE_TERMS) + _score_terms(folded, FINANCE_EXACT),
        "rnd": _score_terms(folded, RND_TERMS),
    }
    best = max(scores.values())
    winners = [name for name, score in scores.items() if score == best and score > 0]
    previous_name = previous if previous in DEPARTMENTS else ""

    if best == 0:
        if _is_smalltalk(folded):
            return RouteDecision("general", "smalltalk", "mock")
        if previous_name:
            return RouteDecision(previous_name, "follow_up", "mock")
        return RouteDecision("general", "ambiguous", "mock")
    if len(winners) == 1:
        return RouteDecision(winners[0], "keyword", "mock")
    if previous_name in winners:
        return RouteDecision(previous_name, "follow_up", "mock")
    if "proje" in folded:
        return RouteDecision("brief", "keyword", "mock")
    return RouteDecision("general", "ambiguous", "mock")


def _parse_route(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    raw = text
    if match:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            raw = str(payload.get("route", ""))
    aliases = {
        "market": "market",
        "pazar": "market",
        "operasyon": "market",
        "satis": "market",
        "finance": "finance",
        "finans": "finance",
        "muhasebe": "finance",
        "rnd": "rnd",
        "arge": "rnd",
        "ar-ge": "rnd",
        "teknik": "rnd",
        "brief": "brief",
        "yonetici": "brief",
        "repo": "brief",
        "general": "general",
        "genel": "general",
        "supervisor": "general",
    }
    return aliases.get(fold(raw).strip())


ROUTING_PROMPT = (
    "Sen BCD TECHNOLOGIES içindeki yönlendiricisin. İsteği tek bir route değerine ayır.\n"
    "market: sektör, müşteri, satış stratejisi.\n"
    "finance: gider, maliyet, fiyat, kâr.\n"
    "rnd: kod, kütüphane, Ar-Ge yol haritası.\n"
    "brief: GitHub deposu veya pazar, teknik ve finansın birlikte istendiği inceleme.\n"
    "general: selamlama veya belirsiz istek.\n"
    "Kısa takip cümlesinde önceki akışı koru."
)


def routing_prompt() -> str:
    return compose_prompt("supervisor", ROUTING_PROMPT)


def _llm_route(query: str, previous: str) -> str | None:
    prompt = routing_prompt()
    model = bind_agent_model(
        get_settings(),
        agent_temperature("supervisor"),
        schema=DepartmentRoute,
    )
    result = model.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Önceki akış: {previous or 'yok'}\nİstek: {query}"),
        ]
    )
    if isinstance(result, DepartmentRoute):
        return _parse_route(result.route)
    if isinstance(result, dict):
        return _parse_route(str(result.get("route", "")))
    return None


def decide_route(query: str, previous: str = "") -> RouteDecision:
    settings = get_settings()
    if settings.configured and not extract_github_url(query):
        try:
            route = _llm_route(query, previous)
        except Exception as exc:
            logger.warning(
                "LLM yönlendirmesi başarısız, kural tabanına düşüldü: %s",
                describe_llm_error(exc),
            )
        else:
            if route:
                return RouteDecision(route, "llm", "llm")
    return heuristic_route(query, previous)


def general_reply(reason: str) -> str:
    if reason == "ambiguous":
        opening = "İsteği tek bir akışa bağlayamadım. Biraz daha net yazar mısınız?"
    elif reason == "empty":
        opening = "Bir istek yazmadınız."
    elif reason == "github_error":
        opening = "GitHub deposu okunamadı."
    else:
        opening = "Ben BCD TECHNOLOGIES çoklu ajan yöneticisiyim. Depo, pazar, Ar-Ge ve finans işlerini ilgili uzmana alırım."
    lines = [opening, ""]
    for agent in AGENTS:
        if agent["id"] == "supervisor":
            continue
        lines.append(f"- {agent['name']}: {agent['description']}")
    lines.append("")
    lines.append('Örnek: "https://github.com/bariscandasci/ankaras" veya "Aylık sabit giderleri çıkar".')
    return "\n".join(lines)


def _slug_from_fetch(text: str) -> str:
    for line in text.splitlines():
        if line.lower().startswith("slug:"):
            return line.split(":", 1)[1].strip()
    return ""


def supervisor_node(state: AgentState) -> dict:
    announce("supervisor", "Yönetici")
    started = time.perf_counter()
    query = last_user_text(list(state.get("messages") or []))
    previous = state.get("department") or ""
    if previous == "supervisor":
        previous = ""
    url = extract_github_url(query)
    if url:
        outcome = str(fetch_github_repo.invoke({"repo_url": url}))
        step = observe("supervisor", "Yönetici", ["fetch_github_repo"], started)
        if outcome.startswith("Hata"):
            return {
                "messages": [AIMessage(content=f"{outcome}\n\n{general_reply('github_error')}", name="supervisor")],
                "department": "supervisor",
                "route": "general",
                "reason": "github_error",
                "mode": "mock",
                "tools_used": ["fetch_github_repo"],
                "trace": [step],
            }
        return {
            "route": "brief",
            "reason": "github",
            "project_slug": _slug_from_fetch(outcome),
            "department": "brief",
            "trace": [step],
        }
    decision = decide_route(query, previous)
    step = observe("supervisor", "Yönetici", [], started)
    update: dict = {"route": decision.route, "reason": decision.reason, "trace": [step]}
    if decision.route == "general":
        update.update(
            {
                "messages": [AIMessage(content=general_reply(decision.reason), name="supervisor")],
                "department": "supervisor",
                "mode": decision.mode,
                "tools_used": [],
            }
        )
    return update

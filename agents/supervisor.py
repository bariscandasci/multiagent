"""İsteği departman ajanına ayıran yönetici."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage

from agents.catalog import AGENTS
from agents.runtime import last_user_text, message_text
from agents.state import AgentState
from config import get_chat_model, get_settings
from tools.common import contains_term, fold, mentions_record
from tools.finance_tools import INVOICES
from tools.hr_tools import CANDIDATES, EMPLOYEES
from tools.ops_tools import SERVERS

logger = logging.getLogger(__name__)

DEPARTMENTS = {"hr", "finance", "ops"}

HR_TERMS = (
    "personel",
    "calisan",
    "aday",
    "ise alim",
    "mulakat",
    "kadro",
    "izin",
    "insan kaynak",
    "bordro",
    "cv",
    "headcount",
    "maas",
    "ucret",
    "ekip",
)
FINANCE_TERMS = (
    "gelir",
    "gider",
    "fatura",
    "butce",
    "muhasebe",
    "tahsilat",
    "odeme",
    "nakit",
    "maliyet",
    "bilanco",
    "karlilik",
    "kar marji",
    "alacak",
    "borc",
)
FINANCE_EXACT = ("kar", "zarar")
OPS_TERMS = (
    "sunucu",
    "sistem durum",
    "cpu",
    "bellek",
    "disk",
    "incident",
    "kesinti",
    "deploy",
    "bakim",
    "uptime",
    "devops",
    "heartbeat",
    "servis durum",
    "teknik gorev",
    "is plani",
    "ariza",
    "olay kaydi",
)
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


def _score_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if contains_term(text, term))


def _apply_record_signals(text: str, scores: dict[str, int]) -> None:
    for person in EMPLOYEES:
        if mentions_record(text, name=str(person["name"]), record_id=str(person["id"])):
            scores["hr"] += 3
            break
    for candidate in CANDIDATES:
        if mentions_record(text, name=candidate["name"], record_id=candidate["id"]):
            scores["hr"] += 3
            break
    for invoice in INVOICES:
        if contains_term(text, fold(str(invoice["id"]))):
            scores["finance"] += 3
            break
    for server in SERVERS:
        if contains_term(text, fold(str(server["name"]))):
            scores["ops"] += 3
            break
    if re.search(r"(?<![a-z0-9])inc-\d+", text):
        scores["ops"] += 3


def _is_smalltalk(text: str) -> bool:
    return any(contains_term(text, term) for term in SMALLTALK)


def heuristic_route(query: str, previous: str = "") -> RouteDecision:
    """Anahtarsız yönlendirme. Testler bu fonksiyonu sabitler."""
    folded = fold(query)
    if not folded.strip():
        return RouteDecision("general", "empty", "mock")

    scores = {
        "hr": _score_terms(folded, HR_TERMS),
        "finance": _score_terms(folded, FINANCE_TERMS) + _score_terms(folded, FINANCE_EXACT),
        "ops": _score_terms(folded, OPS_TERMS),
    }
    _apply_record_signals(folded, scores)
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
        "hr": "hr",
        "ik": "hr",
        "insan kaynaklari": "hr",
        "finance": "finance",
        "finans": "finance",
        "muhasebe": "finance",
        "ops": "ops",
        "operasyon": "ops",
        "teknik": "ops",
        "general": "general",
        "genel": "general",
        "supervisor": "general",
    }
    return aliases.get(fold(raw).strip())


def _llm_route(query: str, previous: str) -> str | None:
    prompt = (
        "Sen bir şirket içi yönlendiricisin. İsteği tek bir değere ayır.\n"
        "İzin verilen route değerleri: hr, finance, ops, general.\n"
        "hr: personel, aday, kadro, izin.\n"
        "finance: gelir, gider, fatura, bütçe, tahsilat.\n"
        "ops: sunucu, kesinti, bakım, teknik iş planı.\n"
        "general: selamlama, yetenek sorusu veya belirsiz istek.\n"
        f"Önceki departman: {previous or 'yok'}. Kısa takip cümlesinde önceki departmanı koru.\n"
        'Yanıtı yalnızca JSON ver: {"route": "hr"}\n\n'
        f"İstek: {query}"
    )
    result = get_chat_model().invoke([HumanMessage(content=prompt)])
    return _parse_route(message_text(result.content))


def decide_route(query: str, previous: str = "") -> RouteDecision:
    settings = get_settings()
    if settings.configured:
        try:
            route = _llm_route(query, previous)
        except Exception as exc:
            logger.warning("LLM yönlendirmesi başarısız, kural tabanına düşüldü: %s", exc.__class__.__name__)
        else:
            if route:
                return RouteDecision(route, "llm", "llm")
    return heuristic_route(query, previous)


def general_reply(reason: str) -> str:
    if reason == "ambiguous":
        opening = "İsteği tek bir departmana bağlayamadım. Biraz daha net yazar mısınız?"
    elif reason == "empty":
        opening = "Bir istek yazmadınız."
    else:
        opening = "Ben şirket içi çoklu ajan yöneticisiyim. İsteğinizi ilgili departmana yönlendiririm."
    lines = [opening, ""]
    for agent in AGENTS:
        if agent["id"] == "supervisor":
            continue
        lines.append(f"- {agent['name']}: {agent['description']}")
    lines.append("")
    lines.append('Örnek: "Açık faturaları listele" veya "db-01 durumunu kontrol et".')
    return "\n".join(lines)


def supervisor_node(state: AgentState) -> dict:
    query = last_user_text(list(state.get("messages") or []))
    previous = state.get("department") or ""
    if previous == "supervisor":
        previous = ""
    decision = decide_route(query, previous)
    update: dict = {"route": decision.route, "reason": decision.reason}
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

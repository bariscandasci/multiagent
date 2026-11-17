"""Süreç içi oturum belleği. Kalıcı depo bu MVP'de yoktur."""

from __future__ import annotations

import logging
import re
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agents.graph import build_graph

logger = logging.getLogger(__name__)


def clean_session_id(value: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", (value or "").strip())[:64]
    return cleaned or uuid4().hex


def latest_answer(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            content = message.content
            if isinstance(content, str):
                return content
            return str(content)
    return ""


class Orchestrator:
    """Tek süreçte oturumları MemorySaver ile tutar."""

    def __init__(self) -> None:
        self.checkpointer = MemorySaver()
        self.graph = build_graph(checkpointer=self.checkpointer)

    def ask(self, message: str, session_id: str | None = None) -> dict:
        thread_id = clean_session_id(session_id)
        try:
            result = self.graph.invoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": thread_id}},
            )
        except Exception as exc:
            logger.exception("Grafik çalıştırılamadı: %s", exc.__class__.__name__)
            return {
                "session_id": thread_id,
                "department": "supervisor",
                "route": "general",
                "reason": "error",
                "mode": "mock",
                "tools_used": [],
                "answer": "İstek işlenirken bir hata oluştu. Lütfen yeniden deneyin.",
            }
        return {
            "session_id": thread_id,
            "department": result.get("department") or "supervisor",
            "route": result.get("route") or "general",
            "reason": result.get("reason") or "",
            "mode": result.get("mode") or "mock",
            "tools_used": list(result.get("tools_used") or []),
            "answer": latest_answer(result.get("messages") or []),
        }


_default: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _default
    if _default is None:
        _default = Orchestrator()
    return _default


def reset_orchestrator() -> None:
    global _default
    _default = None

"""Ajan adımlarını çalışan isteğe canlı iletmek için."""

from __future__ import annotations

import contextvars
import time
from collections.abc import Callable

_sink: contextvars.ContextVar[Callable[[dict], None] | None] = contextvars.ContextVar(
    "agent_progress",
    default=None,
)


def bind_progress(sink: Callable[[dict], None]):
    return _sink.set(sink)


def reset_progress(token) -> None:
    _sink.reset(token)


def emit_progress(step: dict) -> None:
    sink = _sink.get()
    if sink is not None:
        sink(dict(step))


def announce(agent_id: str, label: str) -> None:
    """Ajan işe başlamadan önce arayüze 'çalışıyor' durumu yollar."""
    emit_progress(
        {
            "phase": "agent",
            "id": agent_id,
            "label": label,
            "tools": [],
            "duration_ms": None,
            "status": "running",
        }
    )


def publish_section(section_id: str, text: str) -> None:
    """Tam bölüm metnini sekmeye yollar. Sonraki ajana giden özet bundan ayrıdır."""
    from agents.handoff import compact_handoff

    emit_progress(
        {
            "phase": "section",
            "id": section_id,
            "section": section_id,
            "text": text,
            "summary": compact_handoff(text),
            "status": "done",
        }
    )


def observe(agent_id: str, label: str, tools: list[str], started: float) -> dict:
    step = {
        "id": agent_id,
        "label": label,
        "tools": list(tools),
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "status": "done",
    }
    emit_progress({"phase": "agent", **step})
    return step

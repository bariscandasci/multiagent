"""Departman ajanlarının ortak araç döngüsü."""

from __future__ import annotations

import logging
from collections.abc import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from config import Settings, get_chat_model, get_settings
from tools.common import DISCLAIMER

logger = logging.getLogger(__name__)

PlanCalls = Callable[[str], list[tuple[str, dict]]]


def message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                text = getattr(block, "text", None)
                parts.append(str(text if text is not None else block))
        return "".join(parts)
    return str(content)


def user_texts(messages: list) -> list[str]:
    texts: list[str] = []
    for message in messages:
        role = getattr(message, "type", None) or getattr(message, "role", None)
        if role in {"human", "user"}:
            texts.append(message_text(getattr(message, "content", "")))
    return texts


def last_user_text(messages: list) -> str:
    texts = user_texts(messages)
    return texts[-1] if texts else ""


def execute_tool(tools: list, name: str, args: dict | None) -> str:
    mapping = {tool.name: tool for tool in tools}
    tool = mapping.get(name)
    if tool is None:
        return f"Bilinmeyen araç: {name}"
    payload = {key: value for key, value in (args or {}).items() if value is not None}
    try:
        return str(tool.invoke(payload))
    except Exception as exc:
        logger.warning("Araç çağrısı başarısız: %s (%s)", name, exc.__class__.__name__)
        return f"{name} çalıştırılamadı."


def render_mock(title: str, messages: list, tools: list, plan_calls: PlanCalls) -> tuple[str, list[str]]:
    context = "\n".join(user_texts(messages)[-4:])
    calls = plan_calls(context)[:3]
    used: list[str] = []
    chunks: list[str] = []
    for name, args in calls:
        used.append(name)
        chunks.append(execute_tool(tools, name, args))
    body = "\n\n".join(chunk for chunk in chunks if chunk).strip() or "Bu istek için araç sonucu oluşmadı."
    return f"{title}\n\n{body}\n\n{DISCLAIMER}", used


def _history(messages: list) -> list:
    kept = []
    for message in messages:
        if isinstance(message, (HumanMessage, AIMessage)) and not getattr(message, "tool_calls", None):
            kept.append(message)
    return kept[-8:]


def _call_parts(call: object) -> tuple[str, dict, str]:
    if isinstance(call, dict):
        name = str(call.get("name") or "")
        args = call.get("args") or {}
        call_id = str(call.get("id") or name)
    else:
        name = str(getattr(call, "name", "") or "")
        args = getattr(call, "args", {}) or {}
        call_id = str(getattr(call, "id", "") or name)
    if not isinstance(args, dict):
        args = {}
    return name, args, call_id


def llm_answer(settings: Settings, system_prompt: str, tools: list, messages: list) -> tuple[str, list[str]]:
    model = get_chat_model(settings).bind_tools(tools)
    convo: list = [SystemMessage(content=system_prompt), *_history(messages)]
    used: list[str] = []
    last_tool_text = ""
    for _ in range(4):
        ai = model.invoke(convo)
        calls = getattr(ai, "tool_calls", None) or []
        if not calls:
            return message_text(ai.content).strip(), used
        convo.append(ai)
        for call in calls:
            name, args, call_id = _call_parts(call)
            used.append(name)
            result = execute_tool(tools, name, args)
            last_tool_text = result
            convo.append(ToolMessage(content=result, tool_call_id=call_id))
    return last_tool_text.strip(), used


def run_department(
    state: dict,
    *,
    department: str,
    agent_name: str,
    title: str,
    system_prompt: str,
    tools: list,
    plan_calls: PlanCalls,
) -> dict:
    messages = list(state.get("messages") or [])
    settings = get_settings()
    mode = "mock"
    if settings.configured:
        try:
            answer, used = llm_answer(settings, system_prompt, tools, messages)
        except Exception as exc:
            logger.warning("LLM ajanı başarısız, mock rapora düşüldü: %s", exc.__class__.__name__)
            answer, used = render_mock(title, messages, tools, plan_calls)
            answer += "\n\nNot: LLM çağrısı başarısız oldu; örnek araç raporu gösterildi."
        else:
            if used and answer.strip():
                mode = "llm"
            else:
                answer, used = render_mock(title, messages, tools, plan_calls)
    else:
        answer, used = render_mock(title, messages, tools, plan_calls)

    return {
        "messages": [AIMessage(content=answer, name=agent_name)],
        "department": department,
        "route": department,
        "mode": mode,
        "tools_used": used,
    }

"""Yönetici ve uzman ajanları tek grafikte birleştirir."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.brief import brief_node
from agents.finance_agent import finance_node
from agents.market_agent import market_node
from agents.rnd_agent import rnd_node
from agents.state import AgentState
from agents.supervisor import supervisor_node


def route_next(state: AgentState) -> str:
    route = state.get("route") or "general"
    if route not in {"market", "finance", "rnd", "brief", "general"}:
        return "general"
    return route


def build_graph(checkpointer=None):
    """Supervisor isteği pazar, finans, Ar-Ge veya bütünleşik rapora yollar."""
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("market_agent", market_node)
    builder.add_node("finance_agent", finance_node)
    builder.add_node("rnd_agent", rnd_node)
    builder.add_node("brief", brief_node)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_next,
        {
            "market": "market_agent",
            "finance": "finance_agent",
            "rnd": "rnd_agent",
            "brief": "brief",
            "general": END,
        },
    )
    builder.add_edge("market_agent", END)
    builder.add_edge("finance_agent", END)
    builder.add_edge("rnd_agent", END)
    builder.add_edge("brief", END)
    return builder.compile(checkpointer=checkpointer)

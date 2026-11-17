"""Yönetici ve departman ajanlarını tek grafikte birleştirir."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.finance_agent import finance_node
from agents.hr_agent import hr_node
from agents.ops_agent import ops_node
from agents.state import AgentState
from agents.supervisor import supervisor_node


def route_next(state: AgentState) -> str:
    route = state.get("route") or "general"
    if route not in {"hr", "finance", "ops", "general"}:
        return "general"
    return route


def build_graph(checkpointer=None):
    """Supervisor gelen isteği İK, finans veya operasyon düğümüne yollar."""
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("hr_agent", hr_node)
    builder.add_node("finance_agent", finance_node)
    builder.add_node("ops_agent", ops_node)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_next,
        {
            "hr": "hr_agent",
            "finance": "finance_agent",
            "ops": "ops_agent",
            "general": END,
        },
    )
    builder.add_edge("hr_agent", END)
    builder.add_edge("finance_agent", END)
    builder.add_edge("ops_agent", END)
    return builder.compile(checkpointer=checkpointer)

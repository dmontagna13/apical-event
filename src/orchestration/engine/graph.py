"""LangGraph StateGraph definition for the deliberation loop (§4.4)."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes.aggregation import agent_aggregation_node
from .nodes.dispatch import agent_dispatch_node
from .nodes.human_gate import human_gate_node, route_after_human_gate
from .nodes.moderator import moderator_turn_node
from .state import EngineState


def build_graph() -> StateGraph:
    """Construct and compile the deliberation StateGraph."""

    graph = StateGraph(EngineState)

    graph.add_node("agent_aggregation", agent_aggregation_node)
    graph.add_node("moderator_turn", moderator_turn_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("agent_dispatch", agent_dispatch_node)

    graph.set_entry_point("agent_aggregation")

    graph.add_edge("agent_aggregation", "moderator_turn")
    graph.add_edge("moderator_turn", "human_gate")

    graph.add_conditional_edges(
        "human_gate",
        route_after_human_gate,
        {
            "agent_dispatch": "agent_dispatch",
            "moderator_turn": "moderator_turn",
            "consensus": END,
        },
    )

    graph.add_edge("agent_dispatch", "agent_aggregation")

    compiled = graph.compile()
    compiled.entry_point = "agent_aggregation"
    return compiled

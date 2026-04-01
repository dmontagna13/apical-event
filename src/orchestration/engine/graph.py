"""LangGraph StateGraph definition for the deliberation loop (§4.4).

DECISION: This module defines the graph structure for documentation and
type-checking purposes.  The runner (runner.py) executes nodes directly via
an asyncio loop rather than calling compiled.ainvoke().  This avoids
LangGraph's checkpoint infrastructure while still using LangGraph's TypedDict
state and node conventions.  The graph is compile-able and the topology is
inspectable, but production execution goes through runner._run_graph().

The four-node cycle:
    moderator_turn → human_gate → agent_dispatch → agent_aggregation → (back to moderator_turn)

Escape paths:
    human_gate → moderator_turn  (chat-only, no cards approved)
    any node    → consensus      (all Kanban tasks RESOLVED)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes.aggregation import agent_aggregation_node
from .nodes.dispatch import agent_dispatch_node
from .nodes.human_gate import human_gate_node
from .nodes.moderator import moderator_turn_node
from .state import GraphState


def build_graph() -> StateGraph:
    """Construct the deliberation StateGraph.

    The compiled graph is used for topology inspection.  See runner.py for
    the actual async execution loop.
    """

    graph = StateGraph(GraphState)

    graph.add_node("moderator_turn", moderator_turn_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("agent_dispatch", agent_dispatch_node)
    graph.add_node("agent_aggregation", agent_aggregation_node)

    graph.set_entry_point("moderator_turn")

    graph.add_edge("moderator_turn", "human_gate")
    graph.add_edge("agent_dispatch", "agent_aggregation")
    graph.add_edge("agent_aggregation", "moderator_turn")

    # human_gate routes conditionally (handled in runner via direct node calls)
    graph.add_edge("human_gate", END)

    return graph

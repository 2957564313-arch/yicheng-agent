from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.container import AppContainer
from app.nodes.enrich import make_enrich_node
from app.nodes.plan import make_plan_node
from app.nodes.respond import make_respond_node
from app.nodes.understand import make_understand_node
from app.nodes.validate import make_validate_node
from app.state import CampusAgentState


def route_after_understand(state: CampusAgentState) -> str:
    return "respond" if state.get("clarifications") else "enrich"


def route_after_enrich(state: CampusAgentState) -> str:
    return "respond" if state.get("intent") == "query" else "plan"


def route_after_validate(state: CampusAgentState) -> str:
    # The planner is deterministic and does not mutate its candidate domain
    # from validation issues. Re-entering it with the same state would only
    # reproduce the same invalid plan and waste latency. Return the validator's
    # precise issues to the user; explicit event replanning rebuilds context.
    return "respond"


def build_graph(
    container: AppContainer,
    *,
    checkpointer: Any | None = None,
):
    builder = StateGraph(CampusAgentState)
    builder.add_node("understand", make_understand_node(container))
    builder.add_node("enrich", make_enrich_node(container))
    builder.add_node("plan", make_plan_node(container))
    builder.add_node("validate", make_validate_node(container))
    builder.add_node("respond", make_respond_node(container))

    builder.add_edge(START, "understand")
    builder.add_conditional_edges(
        "understand",
        route_after_understand,
        {"enrich": "enrich", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "enrich",
        route_after_enrich,
        {"respond": "respond", "plan": "plan"},
    )
    builder.add_edge("plan", "validate")
    builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {"plan": "plan", "respond": "respond"},
    )
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer)

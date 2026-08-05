from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.coordinator import coordinator_finalize, coordinator_intake
from src.agents.delivery_agent import delivery_node
from src.agents.order_seller_agent import order_seller_node
from src.agents.payment_agent import payment_node
from src.agents.policy_agent import policy_node
from src.agents.verifier_agent import verifier_node
from src.state import CaseState


def build_graph():
    graph = StateGraph(CaseState)
    graph.add_node("coordinator_intake", coordinator_intake)
    graph.add_node("order_seller", order_seller_node)
    graph.add_node("delivery", delivery_node)
    graph.add_node("payment", payment_node)
    graph.add_node("policy", policy_node)
    graph.add_node("coordinator_finalize", coordinator_finalize)
    graph.add_node("verifier", verifier_node)

    graph.set_entry_point("coordinator_intake")
    graph.add_edge("coordinator_intake", "order_seller")
    graph.add_edge("order_seller", "delivery")
    graph.add_edge("delivery", "payment")
    graph.add_edge("payment", "policy")
    graph.add_edge("policy", "coordinator_finalize")
    graph.add_edge("coordinator_finalize", "verifier")
    graph.add_edge("verifier", END)

    return graph.compile()

from langgraph.graph import END, START, StateGraph

from app.graph import nodes as N
from app.graph.state import AgentState


def build_graph(checkpointer, runtime):
    b = StateGraph(AgentState)
    b.add_node("classify_intent", N.classify_node(runtime))
    b.add_node("agent", N.agent_node(runtime))
    b.add_node("gate_node", N.gate_node(runtime))          # write-action approval (Command-routed)
    b.add_node("execute_action", N.execute_action_node(runtime))
    b.add_node("draft_reply", N.draft_reply_node(runtime))
    b.add_node("review_gate", N.review_gate_node(runtime))  # low-confidence draft review
    b.add_node("escalate_node", N.escalate_node(runtime))

    b.add_edge(START, "classify_intent")
    b.add_edge("classify_intent", "agent")
    b.add_edge("execute_action", "draft_reply")
    b.add_edge("draft_reply", "review_gate")
    b.add_edge("review_gate", END)
    b.add_edge("escalate_node", END)
    # agent / gate_node route via Command(goto=...) returned at runtime
    return b.compile(checkpointer=checkpointer)
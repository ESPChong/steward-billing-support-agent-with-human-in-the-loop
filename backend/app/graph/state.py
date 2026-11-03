from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    thread_id: str
    customer_id: str
    intent: str                 # faq | billing_inquiry | refund_request | plan_change | pii_change | other
    confidence: float
    sentiment: str              # positive | neutral | angry
    review_reasons: list[str]   # low-confidence / angry flags -> draft review gate
    pending_action: Optional[dict]
    action_result: Optional[dict]
    policy_ref: Optional[str]
    revisions: int
    reviewer_feedback: Optional[str]
    escalation: Optional[str]
    escalated: bool
    final_reply: str
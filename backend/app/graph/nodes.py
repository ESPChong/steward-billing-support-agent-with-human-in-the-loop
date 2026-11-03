"""Graph nodes. Gate nodes are small + pure: on resume they re-execute and
interrupt() returns the reviewer's decision instead of pausing again."""
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command, interrupt

from app import db
from app.config import settings

INTENTS = ("faq", "billing_inquiry", "refund_request", "plan_change", "pii_change", "other")

CLASSIFY_SYSTEM = """You are the intent-classifier for a SaaS billing support desk.
Given the customer's latest message, respond with ONLY a JSON object:
{"intent": one of [faq, billing_inquiry, refund_request, plan_change, pii_change, other],
 "confidence": float between 0 and 1,
 "sentiment": one of [positive, neutral, angry]}"""

AGENT_SYSTEM = """You are Steward, the billing-support-agent for a SaaS company.
Rules:
- Always look up facts with read tools (get_subscription, get_invoices, search_billing_policies)
  before answering. Cite policy titles from search results when relevant.
- Write tools (issue_refund, change_plan, update_billing_email) may only be requested when the
  customer clearly asked for the change AND it matches policy from search_billing_policies.
  Write requests pause for human approval — never claim an action is done before you see its
  result message.
- If a reviewer rejected your action (see "[reviewer rejected]" messages), do NOT call the same
  write tool again. Explain politely and offer to escalate.
- If the request is out of scope, involves legal/PII risk, or the customer is irate, call
  escalate_to_human with a short summary.
- Be concise and specific."""

DRAFT_SYSTEM = """You are the reply-drafter for a SaaS billing support desk.
Write the final customer-facing reply based ONLY on the conversation and tool results above.
Reference the relevant policy by name when one applies. Do not promise actions that were not
executed. Keep it under 150 words, warm and specific."""


def _last_human(state) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def classify_node(runtime):
    async def node(state):
        model = runtime.classify_model()
        resp = await model.ainvoke([SystemMessage(content=CLASSIFY_SYSTEM),
                                    HumanMessage(content=_last_human(state))])
        try:
            data = json.loads(resp.content)
            intent = data["intent"] if data["intent"] in INTENTS else "other"
            confidence = min(max(float(data.get("confidence", 0.5)), 0.0), 1.0)
            sentiment = data.get("sentiment", "neutral")
            if sentiment not in ("positive", "neutral", "angry"):
                sentiment = "neutral"
        except Exception:
            intent, confidence, sentiment = "other", 0.5, "neutral"  # conservative -> gates fire
        reasons = []
        if confidence < settings.confidence_floor:
            reasons.append(f"classification confidence {confidence:.2f} below floor {settings.confidence_floor}")
        if intent == "other":
            reasons.append("intent unclear")
        if sentiment == "angry":
            reasons.append("angry sentiment")
        return {"intent": intent, "confidence": confidence, "sentiment": sentiment,
                "review_reasons": reasons, "escalation": None, "escalated": False}
    return node


def _coerce(name, args):
    args = dict(args or {})
    if name == "issue_refund":
        args["invoice_id"] = str(args.get("invoice_id", ""))
        try:
            args["amount_cents"] = int(str(args.get("amount_cents", 0)))
        except ValueError:
            args["amount_cents"] = 0
        args["reason"] = str(args.get("reason", ""))
    if name == "update_billing_email":
        args["new_email"] = str(args.get("new_email", ""))
    if name == "change_plan":
        args["tier"] = str(args.get("tier", "")).lower()
        args["action"] = str(args.get("action", "")).lower()
    if name == "search_billing_policies":
        args["query"] = str(args.get("query", ""))
    return args


def _write_reasons(name, args):
    reasons = ["write actions require human approval"]
    if name == "issue_refund" and int(args.get("amount_cents", 0)) > settings.refund_threshold_cents:
        reasons.append(f"refund ${args['amount_cents'] / 100:.2f} exceeds the "
                       f"${settings.refund_threshold_cents / 100:.2f} auto-approval threshold")
    if name == "update_billing_email":
        reasons.append("PII change: billing email modification")
    if name == "change_plan":
        reasons.append("plan change affects recurring billing")
    return reasons


def _policy_ref(messages):
    for m in reversed(messages):
        if isinstance(m, ToolMessage) and m.name == "search_billing_policies":
            try:
                results = json.loads(m.content).get("results", [])
                if results:
                    return results[0]["title"]
            except Exception:
                return None
    return None


def agent_node(runtime):
    from app.tools.specs import ESCALATE_TOOL, WRITE_TOOLS

    async def node(state):
        model = runtime.chat_model().bind_tools(_schemas())
        work = list(state["messages"])
        out = []
        for _ in range(settings.agent_max_tool_rounds):
            resp = await model.ainvoke([SystemMessage(content=AGENT_SYSTEM)] + work)
            out.append(resp)
            if not getattr(resp, "tool_calls", None):
                return Command(goto="draft_reply", update={"messages": out})
            for tc in resp.tool_calls:
                name, args = tc["name"], _coerce(tc["name"], tc.get("args"))
                if name in WRITE_TOOLS:
                    pa = {"tool": name, "args": args, "tool_call_id": tc["id"],
                          "reasons": _write_reasons(name, args),
                          "policy_ref": _policy_ref(work + [resp])}
                    return Command(goto="gate_node",
                                   update={"messages": out, "pending_action": pa,
                                           "policy_ref": pa["policy_ref"]})
                if name in ESCALATE_TOOL:
                    return Command(goto="escalate_node",
                                   update={"messages": out,
                                           "escalation": args.get("summary", "escalation requested"),
                                           "escalated": True})
                result = await _run_read(name, args, state, runtime)
                tm = ToolMessage(content=json.dumps(result), tool_call_id=tc["id"], name=name)
                out.append(tm)
                work.append(resp)
                work.append(tm)
        return Command(goto="draft_reply", update={"messages": out})
    return node


def _schemas():
    from app.tools.specs import tool_schemas
    return tool_schemas()


async def _run_read(name, args, state, runtime):
    cid = state.get("customer_id", "")
    if name == "get_subscription":
        return await db.get_subscription_impl(cid)
    if name == "get_invoices":
        return await db.get_invoices_impl(cid)
    if name == "search_billing_policies":
        return await db.search_policies_impl(runtime.embeddings(), args.get("query", ""))
    return {"error": f"unknown tool {name}"}


def gate_node(runtime):
    """Amount / PII / write-approval gate. Pauses via interrupt(); resumable
    across process restarts thanks to the Postgres checkpointer."""
    async def node(state):
        pa = state.get("pending_action") or {}
        payload = {"kind": "action",
                   "action": {"tool": pa.get("tool"), "args": pa.get("args")},
                   "reasons": list(pa.get("reasons", [])) + list(state.get("review_reasons", [])),
                   "policy_ref": pa.get("policy_ref") or state.get("policy_ref"),
                   "revisions": state.get("revisions", 0)}
        decision = interrupt(payload)
        feedback = str(decision.get("feedback", "") or "")
        if decision.get("approved"):
            return Command(goto="execute_action")
        revisions = state.get("revisions", 0) + 1
        msgs = [ToolMessage(content=f"[reviewer rejected] {feedback}".strip(),
                            tool_call_id=pa.get("tool_call_id", ""))] if pa.get("tool_call_id") else []
        if revisions >= settings.max_revisions:
            return Command(goto="escalate_node",
                           update={"revisions": revisions, "messages": msgs, "escalated": True,
                                   "escalation": f"reviewer rejected the action "
                                                 f"{settings.max_revisions} times. Last feedback: {feedback}"})
        return Command(goto="agent",
                       update={"revisions": revisions, "reviewer_feedback": feedback,
                               "pending_action": None, "messages": msgs})
    return node


def execute_action_node(runtime):
    async def node(state):
        pa = state.get("pending_action") or {}
        result = await db.execute_action_impl(pa.get("tool", ""), pa.get("args", {}),
                                              state.get("customer_id", ""))
        tm = ToolMessage(content=json.dumps({"status": "ok", "tool": pa.get("tool"), "result": result}),
                         tool_call_id=pa.get("tool_call_id", ""))
        await db.log_event(state.get("thread_id", ""), "action",
                           {"tool": pa.get("tool"), "args": pa.get("args"), "result": result})
        return {"messages": [tm], "pending_action": None, "action_result": result}
    return node


def draft_reply_node(runtime):
    async def node(state):
        extra = (f"\nThe reviewer left feedback to incorporate: {state['reviewer_feedback']}"
                 if state.get("reviewer_feedback") else "")
        text = ""
        async for chk in runtime.chat_model().astream(
                [SystemMessage(content=DRAFT_SYSTEM + extra)] + list(state["messages"])):
            if getattr(chk, "content", ""):
                text += str(chk.content)
        if not text.strip():
            text = "Thanks for reaching out — a billing specialist will follow up shortly."
        return {"final_reply": text.strip()}
    return node


def review_gate_node(runtime):
    """Low-confidence / angry reply gate. Interrupts only when classify flagged the turn."""
    async def node(state):
        reasons = state.get("review_reasons") or []
        if not reasons:
            return {}
        payload = {"kind": "draft", "draft": state.get("final_reply", ""), "reasons": reasons,
                   "confidence": state.get("confidence"), "sentiment": state.get("sentiment"),
                   "revisions": state.get("revisions", 0)}
        decision = interrupt(payload)
        feedback = str(decision.get("feedback", "") or "")
        if decision.get("approved"):
            return {"review_reasons": [], "draft_approved": True}
        revisions = state.get("revisions", 0) + 1
        if revisions >= settings.max_revisions:
            return Command(goto="escalate_node",
                           update={"revisions": revisions, "escalated": True,
                                   "escalation": f"reply rejected {settings.max_revisions} times. "
                                                 f"Feedback: {feedback}"})
        return Command(goto="agent",
                       update={"revisions": revisions, "reviewer_feedback": feedback})
    return node


def escalate_node(runtime):
    async def node(state):
        why = state.get("escalation") or "the request needs a human"
        reply = ("Thanks for your patience — I want to make sure this gets the right attention, so I'm "
                 f"handing it to a billing specialist. Summary for the team: {why}")
        await db.log_event(state.get("thread_id", ""), "escalation", {"reason": why})
        return {"final_reply": reply, "escalated": True}
    return node
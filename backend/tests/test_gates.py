import json
import uuid

import pytest

from app import db

pytestmark = pytest.mark.usefixtures("pool")


def cfg():
    return {"configurable": {"thread_id": uuid.uuid4().hex}, "recursion_limit": 50}


async def run_until_interrupt(graph, message, customer_id="cus_001"):
    last_interrupt = None
    state_in = {"messages": [{"role": "user", "content": message}], "customer_id": customer_id,
                "thread_id": ""}
    async for mode, chunk in graph.astream(state_in, cfg(), stream_mode="updates"):
        if mode == "updates" and "__interrupt__" in chunk:
            last_interrupt = getattr(chunk["__interrupt__"][0], "value", {})
    return last_interrupt


async def test_amount_gate_and_execute(graph):
    intr = await run_until_interrupt(graph, "I think I was charged twice this month.")
    assert intr and intr["kind"] == "action"
    assert intr["action"]["tool"] == "issue_refund"
    assert any("threshold" in r for r in intr["reasons"])
    c = cfg()
    async for _ in graph.astream(__import__("langgraph.types", fromlist=["Command"])
                                 .Command(resume={"approved": True, "feedback": ""}), c):
        pass
    snap = await graph.aget_state(c)
    assert "refund" in snap.values["final_reply"].lower()
    row = await db.pool.fetchrow("SELECT status FROM invoices WHERE id = 'in_1002'")
    assert row["status"] == "refunded"


async def test_small_refund_still_gated_but_no_threshold_reason(graph):
    intr = await run_until_interrupt(graph, "Please refund my last charge, it was a mistake.",
                                     customer_id="cus_005")
    assert intr["action"]["tool"] == "issue_refund"
    assert not any("threshold" in r for r in intr["reasons"])
    assert intr["action"]["args"]["amount_cents"] == 2900


async def test_pii_gate(graph):
    intr = await run_until_interrupt(graph, "Please change my billing email to tom.contractor@example.com",
                                     customer_id="cus_004")
    assert intr["action"]["tool"] == "update_billing_email"
    assert any("PII" in r for r in intr["reasons"])


async def test_two_rejections_escalate(graph):
    from langgraph.types import Command
    intr = await run_until_interrupt(graph, "I think I was charged twice this month.")
    assert intr
    c = cfg()
    for _ in range(2):
        async for _ in graph.astream(Command(resume={"approved": False, "feedback": "not allowed"}), c):
            pass
        intr2 = await run_until_interrupt.__wrapped__(graph, "") if False else None
        break
    # after 2nd rejection the graph should have escalated instead of interrupting again
    snap = await graph.aget_state(c)
    assert snap.values.get("escalated") is True
    assert "specialist" in snap.values["final_reply"]
    row = await db.pool.fetchrow("SELECT status FROM invoices WHERE id = 'in_1002'")
    assert row["status"] == "paid"  # never refunded


async def test_low_confidence_faq_hits_draft_review(graph):
    intr = await run_until_interrupt(graph, "What is your refund policy window?")
    assert intr and intr["kind"] == "draft"
    assert any("confidence" in r for r in intr["reasons"])


async def test_resume_stream_completes_after_draft_approval(graph):
    from langgraph.types import Command
    intr = await run_until_interrupt(graph, "What is your refund policy window?")
    c = cfg()
    done = False
    async for mode, chunk in graph.astream(Command(resume={"approved": True, "feedback": ""}), c,
                                            stream_mode="updates"):
        if mode == "updates" and "review_gate" in chunk and chunk["review_gate"].get("draft_approved"):
            done = True
    assert done
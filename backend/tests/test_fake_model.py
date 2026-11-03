import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.fake_model import FakeChatModel
from app.graph.nodes import AGENT_SYSTEM, CLASSIFY_SYSTEM, DRAFT_SYSTEM

model = FakeChatModel()


def classify(text):
    resp = model.invoke([SystemMessage(content=CLASSIFY_SYSTEM), HumanMessage(content=text)])
    return json.loads(resp.content)


def agent_step(history):
    resp = model.bind_tools([]).invoke([SystemMessage(content=AGENT_SYSTEM)] + history)
    return resp


def test_classify_duplicate_charge():
    c = classify("I think I was charged twice for my subscription this month.")
    assert c["intent"] == "refund_request" and c["confidence"] >= 0.6


def test_classify_angry_low_confidence():
    c = classify("This is unacceptable! I already paid!")
    assert c["sentiment"] == "angry" and c["confidence"] < 0.6


def test_classify_email_is_pii():
    assert classify("Please change my billing email to a@b.com")["intent"] == "pii_change"


def test_agent_refund_script():
    h = [HumanMessage(content="I think I was charged twice this month.")]
    r1 = agent_step(h)
    assert r1.tool_calls[0]["name"] == "get_invoices"
    h += [r1]
    h += [{"name": "get_invoices", "content": '{"invoices": [{"invoice_id": "in_1001", "amount_cents": 7900},'
             ' {"invoice_id": "in_1002", "amount_cents": 7900}]}', "tool_call_id": r1.tool_calls[0]["id"]}]
    r3 = agent_step(h + [{"name": "search_billing_policies",
                           "content": '{"results": []}', "tool_call_id": "x"}])
    assert r3.tool_calls[0]["name"] == "issue_refund"
    assert r3.tool_calls[0]["args"] == {"invoice_id": "in_1002", "amount_cents": 7900,
                                        "reason": "duplicate charge"}


def test_draft_mentions_refund():
    h = [SystemMessage(content=DRAFT_SYSTEM),
         HumanMessage(content="refund please"),
         {"name": "issue_refund", "tool_call_id": "t1",
          "content": '{"status": "ok", "tool": "issue_refund",'
                     ' "result": {"invoice_id": "in_1002", "amount_cents": 7900, "refund_event_id": 1}}'}]
    assert "refund" in model.invoke(h).content.lower()
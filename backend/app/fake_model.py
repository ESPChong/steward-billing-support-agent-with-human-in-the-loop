"""Deterministic scripted model + embeddings (AGENT_FAKE_MODEL=true).

Zero network, byte-stable output — used by unit tests, API tests and Playwright
E2E. Detects the active node via markers embedded in each system prompt:

  - "intent-classifier"    -> return classification JSON
  - "billing-support-agent" -> run the tool script (mirrors graph rules)
  - "reply-drafter"        -> return the final customer reply
"""
import hashlib
import itertools
import json
import re
from typing import Any, Iterator, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_ids = itertools.count(1)


def _tc(name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": f"call_{next(_ids)}"}


def _last_human_text(messages: List[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def _tool_names(messages: List[BaseMessage]) -> List[str]:
    return [m.name for m in messages if isinstance(m, ToolMessage)]


def _blob(messages: List[BaseMessage]) -> str:
    return "\n".join(str(m.content) for m in messages)


def _classify(messages: List[BaseMessage]) -> str:
    text = _last_human_text(messages).lower()
    if "policy" in text or "how long" in text or "how quickly" in text or "what happens" in text:
        intent, confidence = "faq", 0.5
    elif any(w in text for w in ("charged twice", "duplicate", "double")):
        intent, confidence = "refund_request", 0.9
    elif "refund" in text:
        intent, confidence = "refund_request", 0.85
    elif "email" in text:
        intent, confidence = "pii_change", 0.95
    elif any(w in text for w in ("upgrade", "downgrade")):
        intent, confidence = "plan_change", 0.9
    elif "cancel" in text:
        intent, confidence = "plan_change", 0.8
    else:
        intent, confidence = "billing_inquiry", 0.7
    angry = any(w in text for w in ("unacceptable", "ridiculous", "furious"))
    if angry:
        confidence = min(confidence, 0.45)
    sentiment = "angry" if angry else "neutral"
    return json.dumps({"intent": intent, "confidence": confidence, "sentiment": sentiment})


def _agent(messages: List[BaseMessage]) -> dict:
    human = _last_human_text(messages).lower()
    tools_done = _tool_names(messages)
    blob = _blob(messages)

    if "[reviewer rejected]" in blob:
        return {"content": "Understood — the action was rejected. I will not retry it. Drafting an apology."}

    if "email" in human:
        if "update_billing_email" not in tools_done:
            m = EMAIL_RE.search(_last_human_text(messages))
            return {"content": "I can update the billing email.",
                    "tool_calls": [_tc("update_billing_email", {"new_email": m.group(0) if m else "new@example.com"})]}
        return {"content": "The billing email has been handled."}

    if any(w in human for w in ("upgrade", "downgrade", "cancel", "plan")):
        if "change_plan" not in tools_done:
            action = "cancel" if "cancel" in human else ("upgrade" if "upgrade" in human else "downgrade")
            tier = "pro" if "pro" in human else ("starter" if "starter" in human else "enterprise")
            return {"content": "I can update the plan.",
                    "tool_calls": [_tc("change_plan", {"tier": tier, "action": action})]}
        return {"content": "The plan change has been handled."}

    if any(w in human for w in ("refund", "charged twice", "duplicate", "double")):
        if "get_invoices" not in tools_done:
            return {"content": "Let me pull up the invoices.", "tool_calls": [_tc("get_invoices", {})]}
        if "search_billing_policies" not in tools_done:
            q = "duplicate charge refund policy" if any(
                w in human for w in ("twice", "double", "duplicate")) else "refund policy"
            return {"content": "Let me check the refund policy.",
                    "tool_calls": [_tc("search_billing_policies", {"query": q})]}
        if "issue_refund" not in tools_done:
            inv = next(m.content for m in reversed(messages)
                       if isinstance(m, ToolMessage) and m.name == "get_invoices")
            ids = re.findall(r'"invoice_id": "([^"]+)"', inv)
            amounts = re.findall(r'"amount_cents": (\d+)', inv)
            reason = "duplicate charge" if any(w in human for w in ("twice", "double", "duplicate")) \
                else "customer requested refund"
            return {"content": "This refund needs approval.",
                    "tool_calls": [_tc("issue_refund", {"invoice_id": ids[-1],
                                                        "amount_cents": int(amounts[-1]),
                                                        "reason": reason})]}
        return {"content": "The refund has been handled."}

    if "search_billing_policies" not in tools_done:
        return {"content": "Let me check our policy documents.",
                "tool_calls": [_tc("search_billing_policies", {"query": _last_human_text(messages)[:60]})]}
    return {"content": "I have the policy details I need."}


def _draft(messages: List[BaseMessage]) -> str:
    blob = _blob(messages)
    if "[reviewer rejected]" in blob:
        return ("I'm sorry — I wasn't able to complete that request automatically. "
                "I'd like to hand this over to a billing specialist who can review it personally. May I do that?")
    for m in reversed(messages):
        if isinstance(m, ToolMessage) and str(m.content).startswith('{"status"'):
            data = json.loads(m.content)
            r = data.get("result", {})
            if data.get("tool") == "issue_refund":
                return (f"Good news — I've issued a refund of ${r['amount_cents'] / 100:.2f} for invoice "
                        f"{r['invoice_id']}. It should appear on your statement within 5-10 business days. "
                        "Is there anything else I can help with?")
            if data.get("tool") == "update_billing_email":
                return (f"Done — your billing email is now {r.get('new_email')}. "
                        "Future invoices will go there. Anything else I can help with?")
            if data.get("tool") == "change_plan":
                done = "canceled at the end of the period" if r.get("action") == "cancel" \
                    else f"now on the {r.get('tier')} plan"
                return f"All set — your subscription is {done}. Anything else I can help with?"
    return ("Here's a quick summary of how our billing policies work: refunds are available within 30 days "
            "of a charge, duplicate charges are always refunded in full, and plan changes take effect at the "
            "start of the next cycle. Would you like me to look at a specific charge?")


def _next_message(messages: List[BaseMessage]) -> AIMessage:
    system = next((str(m.content) for m in messages if isinstance(m, SystemMessage)), "")
    if "intent-classifier" in system:
        return AIMessage(content=_classify(messages))
    if "reply-drafter" in system:
        return AIMessage(content=_draft(messages))
    return AIMessage(**_agent(messages))


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake-steward"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeChatModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=_next_message(list(messages)))])

    def _stream(self, messages, stop=None, run_manager: Optional[CallbackManagerForLLMRun] = None,
                **kwargs) -> Iterator[ChatGenerationChunk]:
        msg = _next_message(list(messages))
        if msg.tool_calls:
            if run_manager:
                run_manager.on_llm_new_token("")
            yield ChatGenerationChunk(message=AIMessageChunk(content=msg.content, tool_calls=msg.tool_calls))
            return
        words = str(msg.content).split(" ")
        for i, w in enumerate(words):
            piece = w + (" " if i < len(words) - 1 else "")
            if run_manager:
                run_manager.on_llm_new_token(piece)
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))


class DeterministicEmbeddings(Embeddings):
    def __init__(self, dim: int = 768):
        self.dim = dim

    def _vec(self, text: str) -> List[float]:
        out = []
        for i in range(self.dim):
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            out.append((h[0] - 128) / 128)
        norm = sum(x * x for x in out) ** 0.5 or 1.0
        return [x / norm for x in out]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vec(text)
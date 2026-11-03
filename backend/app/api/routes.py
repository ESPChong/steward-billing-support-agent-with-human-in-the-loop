import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from langgraph.types import Command

from app import db
from app.api.sse import sse_event, with_heartbeat
from app.tools.specs import WRITE_TOOLS

router = APIRouter(prefix="/api")

CFGT = lambda tid: {"configurable": {"thread_id": tid}, "recursion_limit": 50}  # noqa: E731


class ChatBody(BaseModel):
    message: str
    thread_id: str | None = None
    customer_id: str = "cus_001"


class ApproveBody(BaseModel):
    approved: bool
    feedback: str = ""


class ForkBody(BaseModel):
    checkpoint_id: str


class FeedbackBody(BaseModel):
    rating: int  # 1 or -1


def _current_state(request: Request, thread_id: str):
    return request.app.state.graph.aget_state(CFGT(thread_id))


async def _events_from_updates(upd: dict, thread_id: str):
    """Translate astream `updates` chunks into SSE step events + audit rows."""
    if "__interrupt__" in upd:
        for intr in upd["__interrupt__"]:
            payload = getattr(intr, "value", None) or {}
            await db.log_event(thread_id, "interrupt", payload)
            yield sse_event("interrupt", {"thread_id": thread_id, "payload": payload})
        return
    from langchain_core.messages import AIMessage, ToolMessage
    for node, val in upd.items():
        if not isinstance(val, dict):
            continue

        async def step(label, detail):
            await db.log_event(thread_id, "step", {"label": label, "detail": detail})
            yield sse_event("step", {"thread_id": thread_id, "label": label, "detail": detail})

        if node == "classify_intent":
            yield step("classified", {"intent": val.get("intent"), "confidence": val.get("confidence"),
                                      "sentiment": val.get("sentiment")})
        elif node == "agent":
            for m in val.get("messages", []):
                if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                    for tc in m.tool_calls:
                        label = ("action_requested" if tc["name"] in WRITE_TOOLS else
                                 "escalation_requested" if tc["name"] == "escalate_to_human" else "tool_call")
                        yield step(label, {"tool": tc["name"], "args": tc.get("args", {})})
                elif isinstance(m, ToolMessage):
                    yield step("tool_result", {"tool": m.name})
        elif node == "gate_node":
            if val.get("revisions"):
                yield step("action_rejected", {"revisions": val["revisions"],
                                               "feedback": val.get("reviewer_feedback", "")})
            else:
                yield step("action_approved", {})
        elif node == "execute_action":
            yield step("action_executed", val.get("action_result") or {})
        elif node == "draft_reply":
            yield step("draft_ready", {})
        elif node == "review_gate":
            if val.get("draft_approved"):
                yield step("draft_approved", {})
            elif val.get("revisions"):
                yield step("draft_rejected", {"revisions": val["revisions"],
                                              "feedback": val.get("reviewer_feedback", "")})
        elif node == "escalate_node":
            yield step("escalated", {"reason": val.get("escalation")})


async def _run_stream(request: Request, payload, thread_id: str):
    graph = request.app.state.graph
    interrupted = False
    async for mode, chunk in graph.astream(payload, CFGT(thread_id),
                                           stream_mode=["updates", "messages"]):
        if mode == "updates":
            if "__interrupt__" in chunk:
                interrupted = True
            async for ev in _events_from_updates(chunk, thread_id):
                yield ev
        else:
            msg_chunk, meta = chunk
            if meta.get("langgraph_node") == "draft_reply" and getattr(msg_chunk, "content", ""):
                yield sse_event("token", {"thread_id": thread_id, "text": str(msg_chunk.content)})
    if interrupted:
        return  # stream ends paused; /approve resumes it
    snap = await _current_state(request, thread_id)
    values = snap.values or {}
    fr = values.get("final_reply", "")
    if fr:
        await db.log_event(thread_id, "message_agent", {"content": fr})
    yield sse_event("done", {"thread_id": thread_id, "final_reply": fr,
                             "status": "escalated" if values.get("escalated") else "done"})


@router.post("/chat/stream")
async def chat_stream(body: ChatBody, request: Request):
    thread_id = body.thread_id or uuid4().hex
    await db.upsert_thread(thread_id, body.customer_id, body.message[:60])
    await db.log_event(thread_id, "message_user", {"content": body.message})
    state_in = {"messages": [HumanMessage(content=body.message)],
                "thread_id": thread_id, "customer_id": body.customer_id}

    async def gen():
        yield sse_event("start", {"thread_id": thread_id})
        async for ev in _run_stream(request, state_in, thread_id):
            yield ev

    return _sse(gen())


@router.post("/threads/{thread_id}/approve")
async def approve(thread_id: str, body: ApproveBody, request: Request):
    snap = await _current_state(request, thread_id)
    if not snap.next:
        raise HTTPException(409, "no pending approval for this thread")
    decision = {"approved": body.approved, "feedback": body.feedback}
    await db.log_event(thread_id, "resume", decision)

    async def gen():
        yield sse_event("resume", {"thread_id": thread_id, "decision": decision})
        async for ev in _run_stream(request, Command(resume=decision), thread_id):
            yield ev

    return _sse(gen())


def _sse(gen):
    return StreamingResponse(with_heartbeat(gen), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/threads")
async def threads():
    return await db.list_threads()


@router.get("/threads/{thread_id}")
async def thread_detail(thread_id: str, request: Request):
    row = await db.get_thread(thread_id)
    if not row:
        raise HTTPException(404, "thread not found")
    snap = await _current_state(request, thread_id)
    values = snap.values or {}
    msgs = [{"role": "user" if m.type == "human" else "assistant", "content": str(m.content)}
            for m in values.get("messages", []) if m.type in ("human", "ai")]
    pending = None
    for t in snap.tasks:
        for intr in (getattr(t, "interrupts", None) or []):
            pending = getattr(intr, "value", None)
    events = await db.fetch_events(thread_id)
    return {"thread": row, "messages": msgs, "events": events, "pending_interrupt": pending,
            "status": "awaiting_approval" if pending else "idle",
            "final_reply": values.get("final_reply"),
            "intent": values.get("intent"), "confidence": values.get("confidence")}


@router.get("/threads/{thread_id}/checkpoints")
async def checkpoints(thread_id: str, request: Request):
    saver = request.app.state.saver
    out = []
    async for tup in saver.alist({"configurable": {"thread_id": thread_id}}, limit=25):
        out.append({"checkpoint_id": tup.config.get("configurable", {}).get("checkpoint_id"),
                    "ts": (tup.checkpoint or {}).get("ts"),
                    "step": (tup.metadata or {}).get("step")})
    return out


@router.post("/threads/{thread_id}/fork")
async def fork(thread_id: str, body: ForkBody, request: Request):
    """Time travel: continue the graph from a past checkpoint under a NEW thread id."""
    src = await db.get_thread(thread_id)
    if not src:
        raise HTTPException(404, "thread not found")
    new_id = uuid4().hex
    await db.upsert_thread(new_id, src["customer_id"] or "cus_001",
                           (src["title"] or "thread") + " (replay)")
    graph = request.app.state.graph
    cfg = {"configurable": {"thread_id": new_id, "checkpoint_id": body.checkpoint_id},
           "recursion_limit": 50}
    async for mode, chunk in graph.astream(None, cfg, stream_mode="updates"):
        async for _ev in _events_from_updates(chunk, new_id):
            pass  # audit-only; drawer re-reads via GET /threads/{id}
    return {"thread_id": new_id}


@router.post("/threads/{thread_id}/feedback")
async def feedback(thread_id: str, body: FeedbackBody):
    if body.rating not in (1, -1):
        raise HTTPException(422, "rating must be 1 or -1")
    await db.add_feedback(thread_id, body.rating)
    await db.log_event(thread_id, "feedback", {"rating": body.rating})
    return {"ok": True}


@router.get("/stats")
async def stats():
    return await db.stats()


@router.get("/customers")
async def customers():
    return await db.list_customers()
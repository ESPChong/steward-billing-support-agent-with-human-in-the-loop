import json
import re

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("pool")


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        ev, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if ev:
            events.append((ev, data))
    return events


@pytest.fixture
async def client():
    from app.main import app
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_chat_interrupt_approve_done(client):
    r = await client.post("/api/chat/stream", json={
        "message": "I think I was charged twice this month.", "customer_id": "cus_001"})
    r.raise_for_status()
    events = parse_sse(r.text)
    labels = [d["label"] for _, d in events if _ == "step"]
    kinds = [e for e, _ in events]
    assert "interrupt" in kinds and "step" in kinds
    assert "action_requested" in labels and "classified" in labels
    thread_id = next(d["thread_id"] for e, d in events if e == "start")

    r2 = await client.post(f"/api/threads/{thread_id}/approve", json={"approved": True})
    r2.raise_for_status()
    events2 = parse_sse(r2.text)
    assert ("done",) and "done" in [e for e, _ in events2]
    done = next(d for e, d in events2 if e == "done")
    assert "refund" in done["final_reply"].lower()


async def test_thread_detail_and_feedback(client):
    r = await client.post("/api/chat/stream", json={
        "message": "What is your refund policy window?", "customer_id": "cus_001"})
    thread_id = next(d["thread_id"] for e, d in parse_sse(r.text) if e == "start")
    detail = (await client.get(f"/api/threads/{thread_id}")).json()
    assert detail["messages"][0]["role"] == "user"
    assert detail["pending_interrupt"]["kind"] == "draft"

    await client.post(f"/api/threads/{thread_id}/approve", json={"approved": True})
    fb = await client.post(f"/api/threads/{thread_id}/feedback", json={"rating": 1})
    assert fb.json()["ok"]
    threads = (await client.get("/api/threads")).json()
    assert any(t["thread_id"] == thread_id for t in threads)
    stats = (await client.get("/api/stats")).json()
    assert stats["feedback_up"] >= 1
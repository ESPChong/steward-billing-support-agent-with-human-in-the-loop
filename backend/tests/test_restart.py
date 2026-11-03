"""The restart-recovery proof: interrupt with saver #1, resume with a brand-new
saver instance (simulating a backend restart) — the approval still completes."""
import uuid

import pytest
from langgraph.checkpoint.postgres import AsyncPostgresSaver
from langgraph.types import Command

from app import db
from app.config import settings
from app.graph.builder import build_graph

pytestmark = pytest.mark.usefixtures("pool")


async def _fresh_saver():
    pool = db.make_pool(settings.checkpoint_db_url)
    pool.kwargs["row_factory"] = None
    del pool.kwargs["row_factory"]
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return saver, pool


async def test_interrupt_survives_saver_recreation(fake_runtime):
    saver1, pool1 = await _fresh_saver()
    graph1 = build_graph(saver1, fake_runtime)
    cfg = {"configurable": {"thread_id": uuid.uuid4().hex}, "recursion_limit": 50}

    interrupted = False
    async for mode, chunk in graph1.astream(
            {"messages": [{"role": "user", "content": "I was charged twice this month."}],
             "customer_id": "cus_001", "thread_id": cfg["configurable"]["thread_id"]},
            cfg, stream_mode="updates"):
        if mode == "updates" and "__interrupt__" in chunk:
            interrupted = True
    assert interrupted
    await pool1.close()  # "process dies"

    saver2, pool2 = await _fresh_saver()  # new process, same Postgres
    graph2 = build_graph(saver2, fake_runtime)
    snap = await graph2.aget_state(cfg)
    assert snap.next, "thread should still be paused at the gate"

    final = None
    async for mode, chunk in graph2.astream(
            Command(resume={"approved": True, "feedback": ""}), cfg, stream_mode="updates"):
        if mode == "updates" and "draft_reply" in chunk:
            final = chunk["draft_reply"].get("final_reply")
    assert final and "refund" in final.lower()
    row = await db.pool.fetchrow("SELECT count(*) AS n FROM refund_events")
    assert row["n"] >= 1
    await pool2.close()
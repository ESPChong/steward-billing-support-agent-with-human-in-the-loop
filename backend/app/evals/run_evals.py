"""`python -m app.evals.run_evals` — run the dataset through the real graph.

Traces land in LangSmith automatically when AGENT_LANGSMITH_* is set
(`make eval-smith`). Extend dataset.json to broaden coverage (~30 cases target).
"""
import asyncio
import json
import os
import uuid
from pathlib import Path

from app import db
from app.config import settings
from app.graph.builder import build_graph
from app.runtime import default_runtime
from langgraph.checkpoint.postgres import AsyncPostgresSaver

HERE = Path(__file__).parent
WRITE_TOOLS = {"issue_refund", "change_plan", "update_billing_email"}


async def run_case(graph, case) -> dict:
    cfg = {"configurable": {"thread_id": uuid.uuid4().hex}, "recursion_limit": 50}
    state_in = {"messages": [{"role": "user", "content": case["message"]}],
                "thread_id": cfg["configurable"]["thread_id"],
                "customer_id": case["customer_id"]}
    # langchain message dicts like {"role": ...} are accepted by add_messages
    intent, tools, interrupt = None, [], None
    async for mode, chunk in graph.astream(state_in, cfg, stream_mode="updates"):
        if mode != "updates":
            continue
        if "__interrupt__" in chunk:
            payload = getattr(chunk["__interrupt__"][0], "value", {}) or {}
            interrupt = payload.get("kind")
            break
        for node, val in chunk.items():
            if not isinstance(val, dict):
                continue
            if node == "classify_intent":
                intent = val.get("intent")
            for m in val.get("messages", []):
                name = getattr(m, "name", None)
                if name:
                    tools.append(name)
    exp = case["expect"]
    ok_intent = intent in (exp["intent"] if isinstance(exp["intent"], list) else [exp["intent"]])
    ok_tools = all(t in tools for t in exp["tools_contain"])
    ok_interrupt = exp["interrupt"] is None or interrupt == exp["interrupt"]
    return {"id": case["id"], "intent": intent, "tools": tools, "interrupt": interrupt,
            "pass": ok_intent and ok_tools and ok_interrupt,
            "why": [] if ok_intent else [f"intent {intent}"] }


async def main():
    db.pool = db.make_pool(settings.database_url)
    await db.pool.open()
    cp_pool = db.make_pool(settings.checkpoint_db_url)
    cp_pool.kwargs["row_factory"] = None
    del cp_pool.kwargs["row_factory"]
    await cp_pool.open()
    saver = AsyncPostgresSaver(cp_pool)
    await saver.setup()
    graph = build_graph(saver, default_runtime())
    cases = json.loads((HERE / "dataset.json").read_text())
    results = []
    for case in cases:
        r = await run_case(graph, case)
        results.append(r)
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"[{mark}] {r['id']:<18} intent={r['intent']} interrupt={r['interrupt']} tools={','.join(r['tools'])}")
    passed = sum(1 for r in results if r["pass"])
    print(f"\n{passed}/{len(results)} cases passed "
          f"({'fake model' if settings.fake_model else settings.chat_model})")
    await db.pool.close()
    await cp_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
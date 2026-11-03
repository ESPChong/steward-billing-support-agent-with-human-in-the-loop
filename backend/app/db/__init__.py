"""Async DB access. `pool` is set by main lifespan (or test fixtures)."""
import json
from typing import Any, List, Optional

from psycopg.rows import dict_row

pool: Optional[Any] = None  # psycopg_pool.AsyncConnectionPool (dict_row)


def _vec_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def log_event(thread_id: str, kind: str, payload: dict) -> None:
    if pool is None or not thread_id:
        return
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO thread_events (thread_id, kind, payload) VALUES (%s, %s, %s)",
                (thread_id, kind, json.dumps(payload)),
            )
            await cur.execute("UPDATE threads SET updated_at = now() WHERE thread_id = %s", (thread_id,))


async def upsert_thread(thread_id: str, customer_id: str, title: str) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO threads (thread_id, customer_id, title) VALUES (%s, %s, %s)"
                " ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()",
                (thread_id, customer_id, title),
            )


async def list_threads(limit: int = 50) -> List[dict]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT thread_id, customer_id, title, created_at, updated_at"
                " FROM threads ORDER BY updated_at DESC LIMIT %s", (limit,))
            rows = await cur.fetchall()
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
        r["updated_at"] = r["updated_at"].isoformat()
    return rows


async def get_thread(thread_id: str) -> Optional[dict]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT thread_id, customer_id, title, created_at, updated_at"
                              " FROM threads WHERE thread_id = %s", (thread_id,))
            r = await cur.fetchone()
    if r:
        r["created_at"] = r["created_at"].isoformat()
        r["updated_at"] = r["updated_at"].isoformat()
    return r


async def fetch_events(thread_id: str) -> List[dict]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT kind, payload, created_at FROM thread_events"
                " WHERE thread_id = %s ORDER BY id ASC", (thread_id,))
            rows = await cur.fetchall()
    return [{"kind": r["kind"], "payload": r["payload"],
             "ts": r["created_at"].isoformat()} for r in rows]


async def list_customers() -> List[dict]:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT c.id, c.name, c.email, s.tier, s.status FROM customers c"
                " LEFT JOIN subscriptions s ON s.customer_id = c.id ORDER BY c.id")
            return await cur.fetchall()


async def add_feedback(thread_id: str, rating: int) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO feedback (thread_id, rating) VALUES (%s, %s)",
                              (thread_id, rating))


async def stats() -> dict:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT"
                " (SELECT count(*) FROM threads) AS threads,"
                " (SELECT count(*) FROM refund_events) AS refunds,"
                " (SELECT count(*) FROM thread_events WHERE kind = 'escalation') AS escalations,"
                " (SELECT count(*) FROM feedback WHERE rating = 1) AS feedback_up,"
                " (SELECT count(*) FROM feedback WHERE rating = -1) AS feedback_down")
            return await cur.fetchone()


# ---------- tool implementations ----------

async def get_subscription_impl(customer_id: str) -> dict:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT s.id, s.tier, s.status, s.monthly_cents, s.period_start, s.period_end"
                " FROM subscriptions s WHERE s.customer_id = %s", (customer_id,))
            row = await cur.fetchone()
    if not row:
        return {"error": "no subscription found"}
    return {"subscription": {k: str(v) for k, v in row.items()}}


async def get_invoices_impl(customer_id: str) -> dict:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, amount_cents, status, period_start, period_end, created_at"
                " FROM invoices WHERE customer_id = %s ORDER BY created_at ASC, id ASC",
                (customer_id,))
            rows = await cur.fetchall()
    return {"invoices": [
        {"invoice_id": r["id"], "amount_cents": r["amount_cents"], "status": r["status"],
         "period_start": str(r["period_start"]), "period_end": str(r["period_end"])} for r in rows]}


async def search_policies_impl(embeddings, query: str) -> dict:
    vec = _vec_literal(embeddings.embed_query(query))
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT d.title, c.content, 1 - (c.embedding <=> %s::vector) AS score"
                " FROM policy_chunks c JOIN policy_documents d ON d.id = c.document_id"
                " ORDER BY c.embedding <=> %s::vector LIMIT 4", (vec, vec))
            rows = await cur.fetchall()
    return {"results": [{"title": r["title"], "content": r["content"],
                         "score": round(float(r["score"]), 4)} for r in rows]}


PLAN_PRICES = {"free": 0, "starter": 2900, "pro": 7900, "enterprise": 29900}


async def execute_action_impl(tool: str, args: dict, customer_id: str) -> dict:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if tool == "issue_refund":
                await cur.execute("SELECT id, amount_cents, status FROM invoices"
                                 " WHERE id = %s AND customer_id = %s", (args.get("invoice_id"), customer_id))
                inv = await cur.fetchone()
                if not inv:
                    return {"error": "invoice not found for this customer"}
                if inv["status"] == "refunded":
                    return {"error": "invoice already refunded"}
                amount = int(args.get("amount_cents", inv["amount_cents"]))
                await cur.execute("UPDATE invoices SET status = 'refunded' WHERE id = %s", (inv["id"],))
                await cur.execute(
                    "INSERT INTO refund_events (invoice_id, customer_id, amount_cents, reason)"
                    " VALUES (%s, %s, %s, %s) RETURNING id",
                    (inv["id"], customer_id, amount, args.get("reason", "")))
                rid = (await cur.fetchone())["id"]
                return {"invoice_id": inv["id"], "amount_cents": amount, "refund_event_id": rid}

            if tool == "change_plan":
                tier = str(args.get("tier", "")).lower()
                action = str(args.get("action", "")).lower()
                if tier not in PLAN_PRICES or action not in ("upgrade", "downgrade", "cancel"):
                    return {"error": f"invalid plan change: tier={tier} action={action}"}
                status = "canceled" if action == "cancel" else "active"
                await cur.execute(
                    "UPDATE subscriptions SET tier = %s, monthly_cents = %s, status = %s,"
                    " updated_at = now() WHERE customer_id = %s",
                    (tier, PLAN_PRICES[tier], status, customer_id))
                return {"tier": tier, "action": action, "monthly_cents": PLAN_PRICES[tier]}

            if tool == "update_billing_email":
                new_email = str(args.get("new_email", ""))
                await cur.execute("UPDATE customers SET billing_email = %s WHERE id = %s",
                                  (new_email, customer_id))
                return {"new_email": new_email}

            return {"error": f"unknown action tool: {tool}"}


def make_pool(conninfo: str):
    from psycopg_pool import AsyncConnectionPool

    return AsyncConnectionPool(conninfo=conninfo, min_size=1, max_size=5, open=False,
                               kwargs={"autocommit": True, "row_factory": dict_row})
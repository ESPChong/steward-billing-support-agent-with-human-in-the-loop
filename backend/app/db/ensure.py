"""`python -m app.db.ensure` — create DBs + schema + seed + KB index.

Safe to run repeatedly; used by local dev, tests and CI. Resets demo data.
"""
import asyncio
import os

import psycopg

from app.config import settings

HERE = os.path.dirname(__file__)


async def ensure_databases() -> None:
    base = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    async with await psycopg.AsyncConnection.connect(base, autocommit=True) as conn:
        for db in ("billing", "agent_checkpoints"):
            try:
                await conn.execute(f'CREATE DATABASE "{db}"')
                print(f"created database {db}")
            except psycopg.errors.DuplicateDatabase:
                pass


async def apply_file(conninfo: str, path: str) -> None:
    with open(path) as f:
        script = f.read()
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        for stmt in script.split(";"):
            if stmt.strip():
                await conn.execute(stmt)


async def main() -> None:
    await ensure_databases()
    await apply_file(settings.database_url, os.path.join(HERE, "01-init.sql"))
    await apply_file(settings.database_url, os.path.join(HERE, "02-seed.sql"))
    print("schema + seed applied")
    from app.ingest import ingest
    await ingest(force=True)
    print("policy KB indexed")


if __name__ == "__main__":
    asyncio.run(main())
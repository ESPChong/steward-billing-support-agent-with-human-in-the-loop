import asyncio
import os
import pathlib

# Env must be set BEFORE importing app modules.
os.environ.setdefault("AGENT_DATABASE_URL", "postgresql://steward:steward@localhost:5432/billing")
os.environ.setdefault("AGENT_CHECKPOINT_DB_URL",
                      "postgresql://steward:steward@localhost:5432/agent_checkpoints")
os.environ.setdefault("AGENT_FAKE_MODEL", "true")

import pytest

from app import db
from app.config import settings
from app.db.ensure import ensure_databases

HERE = pathlib.Path(__file__).resolve().parent.parent / "app" / "db"


async def _bootstrap():
    await ensure_databases()
    await asyncio.get_event_loop().run_in_executor(None, lambda: None)
    from app.db.ensure import apply_file
    await apply_file(settings.database_url, str(HERE / "01-init.sql"))
    await apply_file(settings.database_url, str(HERE / "02-seed.sql"))


@pytest.fixture(scope="session")
async def pool():
    await _bootstrap()
    db.pool = db.make_pool(settings.database_url)
    await db.pool.open()
    from app.ingest import ingest
    await ingest(force=True)  # deterministic embeddings in fake mode
    yield db.pool
    await db.pool.close()
    db.pool = None


@pytest.fixture
def fake_runtime():
    from app.runtime import Runtime
    from app.fake_model import FakeChatModel, DeterministicEmbeddings
    return Runtime(lambda: FakeChatModel(), lambda: FakeChatModel(),
                   lambda: DeterministicEmbeddings(768))


@pytest.fixture
def graph(fake_runtime):
    from langgraph.checkpoint.memory import InMemorySaver
    from app.graph.builder import build_graph
    return build_graph(InMemorySaver(), fake_runtime)
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres import AsyncPostgresSaver

from app import db
from app.api.routes import router
from app.config import settings
from app.graph.builder import build_graph
from app.llm import configure_langsmith
from app.runtime import default_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_langsmith()
    db.pool = db.make_pool(settings.database_url)
    await db.pool.open()
    cp_pool = db.make_pool(settings.checkpoint_db_url)  # saver uses plain tuple rows
    cp_pool.kwargs["row_factory"] = None
    del cp_pool.kwargs["row_factory"]
    await cp_pool.open()
    saver = AsyncPostgresSaver(cp_pool)
    await saver.setup()
    app.state.saver = saver
    app.state.graph = build_graph(saver, default_runtime())
    yield
    await db.pool.close()
    await cp_pool.close()


app = FastAPI(title="Steward — supervised billing agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
async def health():
    return {"ok": True}
"""Chunk + embed docs/policies/*.md into pgvector. Idempotent; --force re-embeds."""
import argparse
import glob
import json
import os
import re

from app.config import settings
from app.db import make_pool, _vec_literal


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > size:  # split oversized paragraphs with sliding window
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:size])
            p = p[max(size - overlap, 1):]
        if len(cur) + len(p) + 2 <= size or not cur:
            cur = (cur + "\n\n" + p).strip()
        else:
            chunks.append(cur)
            cur = (cur[-overlap:] + "\n\n" + p).strip() if overlap else p
    if cur:
        chunks.append(cur)
    return chunks


async def ingest(force: bool = False) -> None:
    from app.llm import get_embeddings

    docs_dir = settings.policy_dir
    files = sorted(glob.glob(os.path.join(docs_dir, "*.md")))
    if not files:
        raise SystemExit(f"no policy files found under {docs_dir}")

    pool = make_pool(settings.database_url)
    await pool.open()
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) AS n FROM policy_chunks")
                existing = (await cur.fetchone())["n"]
                if existing and not force:
                    print(f"policy KB already indexed ({existing} chunks); use --force to reindex")
                    return
                embeddings = get_embeddings()
                for path in files:
                    with open(path) as f:
                        text = f.read()
                    title = text.splitlines()[0].lstrip("# ").strip()
                    doc_id = os.path.splitext(os.path.basename(path))[0]
                    await cur.execute("DELETE FROM policy_chunks WHERE document_id = %s", (doc_id,))
                    await cur.execute("DELETE FROM policy_documents WHERE id = %s", (doc_id,))
                    await cur.execute(
                        "INSERT INTO policy_documents (id, title, source) VALUES (%s, %s, %s)",
                        (doc_id, title, path))
                    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
                    vecs = embeddings.embed_documents(chunks)
                    for i, (chunk, vec) in enumerate(zip(chunks, vecs)):
                        await cur.execute(
                            "INSERT INTO policy_chunks (document_id, chunk_index, content, embedding)"
                            " VALUES (%s, %s, %s, %s::vector)",
                            (doc_id, i, chunk, _vec_literal(vec)))
                print(f"indexed {len(files)} policy documents")
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-embed even if chunks exist")
    asyncio.run(ingest(force=parser.parse_args().force))
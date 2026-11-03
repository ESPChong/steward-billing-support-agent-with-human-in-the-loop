CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS customers (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    billing_email TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id            TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(id),
    tier          TEXT NOT NULL CHECK (tier IN ('free','starter','pro','enterprise')),
    status        TEXT NOT NULL CHECK (status IN ('active','past_due','canceled')),
    monthly_cents INTEGER NOT NULL,
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invoices (
    id            TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(id),
    amount_cents  INTEGER NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('paid','open','past_due','refunded','partially_refunded')),
    period_start  DATE,
    period_end    DATE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refund_events (
    id           BIGSERIAL PRIMARY KEY,
    invoice_id   TEXT NOT NULL REFERENCES invoices(id),
    customer_id  TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    approved_by  TEXT NOT NULL DEFAULT 'human_reviewer',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS threads (
    thread_id   TEXT PRIMARY KEY,
    customer_id TEXT,
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS thread_events (
    id         BIGSERIAL PRIMARY KEY,
    thread_id  TEXT NOT NULL REFERENCES threads(thread_id),
    kind       TEXT NOT NULL,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback (
    id         BIGSERIAL PRIMARY KEY,
    thread_id  TEXT REFERENCES threads(thread_id),
    rating     INTEGER NOT NULL CHECK (rating IN (1, -1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_documents (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    source     TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id TEXT REFERENCES policy_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768)
);

CREATE INDEX IF NOT EXISTS policy_chunks_embedding_idx
    ON policy_chunks USING hnsw (embedding vector_cosine_ops);
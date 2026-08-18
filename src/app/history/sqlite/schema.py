SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    agent_id TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    endpoint TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_model TEXT NOT NULL,
    resolved_model TEXT NOT NULL,
    request_payload BLOB NOT NULL,
    response BLOB,
    usage BLOB,
    error_message TEXT,
    pinned INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_started_at ON entries(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_entries_session ON entries(session_id, started_at DESC);
"""

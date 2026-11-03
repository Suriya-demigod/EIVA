CREATE TABLE IF NOT EXISTS knowledge_sources (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, source_path)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_sources_user ON knowledge_sources(user_id, source_path);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    vector_json TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    UNIQUE (source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_source ON knowledge_chunks(source_id, chunk_index);

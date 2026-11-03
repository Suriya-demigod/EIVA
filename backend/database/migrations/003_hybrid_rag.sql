CREATE TABLE IF NOT EXISTS rag_documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    document_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, source_path)
);

CREATE INDEX IF NOT EXISTS ix_rag_documents_user ON rag_documents(user_id, source_path);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    line_start INTEGER,
    line_end INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (document_id) REFERENCES rag_documents(id) ON DELETE CASCADE,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS ix_rag_chunks_document ON rag_chunks(document_id, chunk_index);

CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    text,
    document_name,
    tokenize='unicode61'
);

-- Preserve the existing M09 lexical index during the hybrid-index upgrade.
INSERT OR IGNORE INTO rag_documents(id, user_id, source_path, document_name, content_hash, updated_at)
SELECT id, user_id, source_path, source_path, content_hash, updated_at FROM knowledge_sources;

INSERT OR IGNORE INTO rag_chunks(document_id, chunk_index, text, page_number, line_start, line_end, metadata_json)
SELECT s.id, c.chunk_index, c.text, NULL, c.start_line, c.end_line, '{"legacy_vector_rebuild_required":true}'
FROM knowledge_chunks c JOIN knowledge_sources s ON s.id=c.source_id;

INSERT OR IGNORE INTO rag_chunks_fts(chunk_id, text, document_name)
SELECT CAST(c.id AS TEXT), c.text, d.document_name
FROM rag_chunks c JOIN rag_documents d ON d.id=c.document_id;

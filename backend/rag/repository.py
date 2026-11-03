"""SQLite, FTS5, and sqlite-vec persistence for RAG documents and chunks."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.database import Database
from backend.rag.models import RagChunk, RagChunkInput, RagDocument

_VECTOR_TABLE = re.compile(r"^rag_vectors_\d+$")


class RagRepository:
    def __init__(self, database: Database, dimensions: int) -> None:
        if dimensions < 1 or dimensions > 4096:
            raise ValueError("Embedding dimensions must be between 1 and 4096")
        self.database = database
        self.dimensions = dimensions
        self.vector_table = f"rag_vectors_{dimensions}"
        database.enable_sqlite_vec()
        with database.connection() as connection:
            connection.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {self.vector_table} USING vec0("
                f"chunk_id INTEGER PRIMARY KEY, user_id TEXT PARTITION KEY, embedding FLOAT[{dimensions}])"
            )

    def get_document(self, user_id: str, source_path: str) -> RagDocument | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM rag_documents d "
                "LEFT JOIN rag_chunks c ON c.document_id=d.id WHERE d.user_id=? AND d.source_path=? GROUP BY d.id",
                (user_id, source_path),
            ).fetchone()
        return self._document(row) if row else None

    def _document(self, row) -> RagDocument:
        return RagDocument(row["id"], row["user_id"], row["source_path"], row["document_name"],
                           row["content_hash"], datetime.fromisoformat(row["updated_at"]), row["chunk_count"])

    def replace_document(self, user_id: str, source_path: str, document_name: str,
                         content_hash: str, chunks: list[RagChunkInput]) -> RagDocument:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT id FROM rag_documents WHERE user_id=? AND source_path=?", (user_id, source_path)
            ).fetchone()
            document_id = row["id"] if row else str(uuid4())
            if row:
                old_ids = [item[0] for item in connection.execute(
                    "SELECT id FROM rag_chunks WHERE document_id=?", (document_id,)
                ).fetchall()]
                self._delete_chunk_indexes(connection, old_ids)
                connection.execute("DELETE FROM rag_chunks WHERE document_id=?", (document_id,))
                connection.execute(
                    "UPDATE rag_documents SET document_name=?, content_hash=?, updated_at=? WHERE id=?",
                    (document_name, content_hash, now, document_id),
                )
            else:
                connection.execute(
                    "INSERT INTO rag_documents(id,user_id,source_path,document_name,content_hash,updated_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (document_id, user_id, source_path, document_name, content_hash, now),
                )
            for index, chunk in enumerate(chunks):
                if len(chunk.embedding) != self.dimensions:
                    raise ValueError(f"Embedding must contain exactly {self.dimensions} dimensions")
                cursor = connection.execute(
                    "INSERT INTO rag_chunks(document_id,chunk_index,text,page_number,line_start,line_end,metadata_json) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (document_id, index, chunk.text, chunk.page_number, chunk.line_start, chunk.line_end,
                     json.dumps(chunk.metadata, ensure_ascii=False)),
                )
                chunk_id = cursor.lastrowid
                connection.execute(
                    "INSERT INTO rag_chunks_fts(chunk_id,text,document_name) VALUES(?,?,?)",
                    (str(chunk_id), f"{chunk.metadata.get('section', '')}\n{chunk.text}".strip(), document_name),
                )
                connection.execute(
                    f"INSERT INTO {self.vector_table}(chunk_id,user_id,embedding) VALUES(?,?,?)",
                    (chunk_id, user_id, json.dumps(chunk.embedding)),
                )
            result = connection.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM rag_documents d "
                "LEFT JOIN rag_chunks c ON c.document_id=d.id WHERE d.id=? GROUP BY d.id", (document_id,)
            ).fetchone()
        return self._document(result)

    def _delete_chunk_indexes(self, connection, chunk_ids: list[int]) -> None:
        vector_tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'rag_vectors_[0-9]*'"
        ).fetchall() if _VECTOR_TABLE.fullmatch(row[0])]
        for chunk_id in chunk_ids:
            connection.execute("DELETE FROM rag_chunks_fts WHERE chunk_id=?", (str(chunk_id),))
            for table in vector_tables:
                connection.execute(f"DELETE FROM {table} WHERE chunk_id=?", (chunk_id,))

    def list_documents(self, user_id: str) -> list[RagDocument]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM rag_documents d "
                "LEFT JOIN rag_chunks c ON c.document_id=d.id WHERE d.user_id=? GROUP BY d.id ORDER BY d.source_path",
                (user_id,),
            ).fetchall()
        return [self._document(row) for row in rows]

    def search_vectors(self, user_id: str, embedding: list[float], limit: int) -> list[tuple[int, float]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT chunk_id,distance FROM {self.vector_table} WHERE embedding MATCH ? "
                "AND user_id=? AND k=? ORDER BY distance",
                (json.dumps(embedding), user_id, limit),
            ).fetchall()
        return [(int(row["chunk_id"]), float(row["distance"])) for row in rows]

    def search_keywords(self, user_id: str, query: str, limit: int) -> list[int]:
        tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
        if not tokens:
            return []
        match = " OR ".join(f'"{token}"' for token in tokens)
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT CAST(f.chunk_id AS INTEGER) AS chunk_id FROM rag_chunks_fts f "
                "JOIN rag_chunks c ON c.id=CAST(f.chunk_id AS INTEGER) "
                "JOIN rag_documents d ON d.id=c.document_id "
                "WHERE rag_chunks_fts MATCH ? AND d.user_id=? ORDER BY bm25(rag_chunks_fts) LIMIT ?",
                (match, user_id, limit),
            ).fetchall()
        return [int(row["chunk_id"]) for row in rows]

    def get_chunks(self, user_id: str, chunk_ids: list[int]) -> dict[int, RagChunk]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT c.*,d.source_path,d.document_name FROM rag_chunks c "
                "JOIN rag_documents d ON d.id=c.document_id "
                f"WHERE d.user_id=? AND c.id IN ({placeholders})",
                (user_id, *chunk_ids),
            ).fetchall()
        return {
            int(row["id"]): RagChunk(
                int(row["id"]), row["document_id"], row["source_path"], row["document_name"], row["text"],
                row["page_number"], row["line_start"], row["line_end"], json.loads(row["metadata_json"]),
            ) for row in rows
        }

    def delete_document(self, document_id: str, user_id: str) -> bool:
        with self.database.connection() as connection:
            document = connection.execute(
                "SELECT id FROM rag_documents WHERE id=? AND user_id=?", (document_id, user_id)
            ).fetchone()
            if not document:
                return False
            chunk_ids = [row[0] for row in connection.execute(
                "SELECT id FROM rag_chunks WHERE document_id=?", (document_id,)
            ).fetchall()]
            self._delete_chunk_indexes(connection, chunk_ids)
            connection.execute("DELETE FROM rag_documents WHERE id=? AND user_id=?", (document_id, user_id))
        return True

"""M09 hybrid RAG evaluation with real SQLite/FTS5/sqlite-vec and fake model calls."""

import asyncio
import hashlib
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
from docx import Document
from fastapi import FastAPI, Request

from backend.api.routes.knowledge import router as knowledge_router
from backend.database import Database
from backend.rag.chunking import chunk_document
from backend.rag.loaders import load_document
from backend.rag.models import DocumentSegment
from backend.rag.repository import RagRepository
from backend.rag.service import RagService


class FakeEmbedder:
    dimensions = 8
    groups = {
        "database": 0, "schema": 0, "migration": 0, "sqlite": 0, "relational": 0, "architecture": 0,
        "garden": 1, "tomato": 1, "sunlight": 1, "sun": 1,
        "manual": 2, "onboarding": 2, "account": 2, "password": 2,
    }

    def _vector(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        for token in re.findall(r"[\w]+", text.casefold()):
            slot = self.groups.get(token, 3 + (int(hashlib.sha256(token.encode()).hexdigest()[:6], 16) % 5))
            values[slot] += 1.0
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._vector(query)


class FakeModelRouter:
    def model_for(self, role: str) -> str:
        assert role == "chat"
        return "fake-groq-model"

    async def complete(self, role: str, messages: list[dict[str, str]], **options):
        prompt = messages[-1]["content"]
        assert "[S1]" in prompt and "database" in prompt.casefold()
        return SimpleNamespace(
            model="fake-groq-model",
            choices=[SimpleNamespace(message=SimpleNamespace(content="Migrations prepare the database schema. [S1] [S999]"))],
        )


def make_text_pdf(path: Path, text: str) -> None:
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    path.write_bytes(output)


async def verify_api(service: RagService, guide_path: Path) -> None:
    app = FastAPI()
    app.include_router(knowledge_router, prefix="/api/v1")
    app.state.rag_service = service

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = uuid4()
        return await call_next(request)

    from backend.core.model_router import get_model_router
    app.dependency_overrides[get_model_router] = FakeModelRouter
    settings = SimpleNamespace(local_user_id="evaluator", context_max_completion_tokens=256)
    with patch("backend.api.routes.knowledge.get_settings", return_value=settings):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://eiva.test") as client:
            index = await client.post("/api/v1/knowledge/index", json={"path": guide_path.name})
            assert index.status_code == 200 and index.json()["indexed"], index.text
            source_id = index.json()["indexed"][0]["id"]
            denied = await client.post("/api/v1/knowledge/index", json={"path": "../outside.txt"})
            assert denied.status_code == 400, denied.text
            search = await client.post(
                "/api/v1/knowledge/search", json={"query": "relational architecture", "limit": 6}
            )
            assert search.status_code == 200 and search.json()["items"], search.text
            answer = await client.post(
                "/api/v1/knowledge/answer", json={"query": "How do migrations prepare schema?", "limit": 6}
            )
            assert answer.status_code == 200, answer.text
            assert "[S1]" in answer.json()["answer"] and "S999" not in answer.json()["answer"]
            citations = answer.json()["citations"]
            assert citations and all(item["source_path"] and item["location"] for item in citations)
            deleted = await client.delete(f"/api/v1/knowledge/sources/{source_id}")
            assert deleted.status_code == 200 and deleted.json()["deleted"]


def verify_legacy_migration(root: Path) -> None:
    partial = root / "partial_migrations"
    partial.mkdir()
    migration_dir = Path(__file__).resolve().parents[1] / "backend" / "database" / "migrations"
    for version in ("001_initial.sql", "002_knowledge_index.sql"):
        (partial / version).write_text((migration_dir / version).read_text(encoding="utf-8"), encoding="utf-8")
    database = Database(root / "legacy.sqlite3", migrations_dir=partial)
    assert database.initialize() == [1, 2]
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO knowledge_sources VALUES(?,?,?,?,?)",
            ("legacy-doc", "evaluator", "knowledge-1/old.md", "oldhash", "2026-11-03T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO knowledge_chunks(id,source_id,chunk_index,text,start_line,end_line,vector_json) "
            "VALUES(?,?,?,?,?,?,?)", ("old-chunk", "legacy-doc", 0, "legacy searchable migration data", 4, 6, "{}"),
        )
    migrated = Database(root / "legacy.sqlite3")
    assert migrated.initialize() == [3]
    repository = RagRepository(migrated, dimensions=8)
    docs = repository.list_documents("evaluator")
    assert len(docs) == 1 and docs[0].source_path == "knowledge-1/old.md"
    assert repository.search_keywords("evaluator", "legacy searchable", 5)


async def main() -> None:
    with TemporaryDirectory(prefix="eiva-hybrid-rag-") as temp:
        base = Path(temp)
        root = base / "knowledge"
        root.mkdir()
        guide = root / "guide.md"
        guide.write_text(
            "# Database lifecycle\nDatabase schema migrations are applied before application startup.\n"
            "SQLite keeps the relational schema versioned.\n", encoding="utf-8"
        )
        code = root / "storage.py"
        code.write_text("class DatabaseStore:\n    def migrate(self):\n        return 'schema migration'\n", encoding="utf-8")
        manual = root / "account.docx"
        docx = Document()
        docx.add_heading("Account manual", level=1)
        docx.add_paragraph("Account onboarding uses a one-time password.")
        docx.save(manual)
        pdf = root / "migration.pdf"
        make_text_pdf(pdf, "Database migration prepares schema before startup")
        (root / "garden.txt").write_text("Tomatoes grow in gardens with sunlight.", encoding="utf-8")

        loaded_pdf = load_document(pdf)
        assert loaded_pdf.segments[0].page_number == 1 and "migration" in loaded_pdf.segments[0].text.casefold()
        loaded_docx = load_document(manual)
        assert loaded_docx.segments and loaded_docx.segments[0].section == "Account manual"
        structured = chunk_document(
            [DocumentSegment("# Heading\n" + ("contextual explanation " * 160) + "\n\n## Next section\nshort text")],
            target_chars=600, overlap_chars=150,
        )
        assert len(structured) >= 3 and any("Next section" in chunk.metadata.get("section", "") for chunk in structured)
        assert all(0 < len(chunk.text) <= 600 for chunk in structured)

        database = Database(base / "rag.sqlite3")
        assert database.initialize() == [1, 2, 3]
        repository = RagRepository(database, dimensions=FakeEmbedder.dimensions)
        service = RagService(repository, FakeEmbedder(), [root], max_file_bytes=1_000_000,
                             chunk_chars=700, overlap_chars=140, candidate_k=12, top_k=6)
        result = service.index_path(".", "evaluator")
        assert len(result["indexed"]) == 5 and not result["skipped"], result["skipped"]
        assert service.search("database migration", "other-user") == []

        keyword_hits = service.search("tomatoes sunlight", "evaluator")
        assert keyword_hits and keyword_hits[0][0].document_name == "garden.txt"
        semantic_hits = service.search("relational architecture", "evaluator")
        assert semantic_hits and semantic_hits[0][0].document_name in {"guide.md", "migration.pdf", "storage.py"}
        pdf_hit = next((chunk for chunk, _ in service.search("database migration startup", "evaluator")
                        if chunk.document_name == "migration.pdf"), None)
        assert pdf_hit and pdf_hit.page_number == 1
        docx_hit = next((chunk for chunk, _ in service.search("account onboarding password", "evaluator")
                         if chunk.document_name == "account.docx"), None)
        assert docx_hit and docx_hit.metadata.get("location_unit") == "paragraph"

        original = next(doc for doc in service.list_documents("evaluator") if doc.document_name == "guide.md")
        guide.write_text("# Updated guide\nThe new cache stores vector embeddings for retrieval.\n", encoding="utf-8")
        updated = service.index_path("guide.md", "evaluator")["indexed"][0]
        assert updated.id == original.id and updated.content_hash != original.content_hash
        assert any(chunk.document_name == "guide.md" for chunk, _ in service.search("vector embeddings", "evaluator"))
        try:
            service.index_path("../outside.txt", "evaluator")
        except ValueError:
            pass
        else:
            raise AssertionError("Path traversal escaped the configured root")
        updated_doc = next(doc for doc in service.list_documents("evaluator") if doc.document_name == "guide.md")
        assert service.delete_document(updated_doc.id, "evaluator")
        assert not service.delete_document(updated_doc.id, "other-user")
        await verify_api(service, guide)
        assert all(chunk.document_name != "guide.md" for chunk, _ in service.search("vector embeddings", "evaluator"))

        verify_legacy_migration(base)

    print("loaders_pdf_docx_text_markdown_code=passed")
    print("structure_aware_chunking_overlap_locations=passed")
    print("sqlite_vec_persistence_and_query=passed")
    print("fts5_keyword_search=passed")
    print("rrf_hybrid_semantic_and_keyword_retrieval=passed")
    print("user_scope_update_delete_path_confinement=passed")
    print("pdf_page_docx_paragraph_citations=passed")
    print("legacy_index_migration=passed")
    print("knowledge_api_groq_router_citations=passed")


if __name__ == "__main__":
    asyncio.run(main())

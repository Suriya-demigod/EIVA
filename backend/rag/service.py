"""Path-confined document ingestion and local hybrid retrieval service."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from pathlib import Path

from backend.rag.chunking import chunk_document
from backend.rag.embeddings import LocalEmbedder
from backend.rag.loaders import DocumentLoadError, SUPPORTED_SUFFIXES, load_document
from backend.rag.models import RagDocument
from backend.rag.repository import RagRepository
from backend.rag.retrieval import HybridRetriever

logger = logging.getLogger("eiva.rag")


class RagError(ValueError):
    pass


class RagService:
    def __init__(self, repository: RagRepository, embedder: LocalEmbedder, allowed_roots: list[Path], *,
                 max_file_bytes: int = 2_000_000, chunk_chars: int = 1100, overlap_chars: int = 175,
                 candidate_k: int = 30, top_k: int = 6) -> None:
        self.repository = repository
        self.embedder = embedder
        self.allowed_roots = [root.expanduser().resolve() for root in allowed_roots]
        self.max_file_bytes = max_file_bytes
        self.chunk_chars = chunk_chars
        self.overlap_chars = overlap_chars
        self.top_k = top_k
        self.retriever = HybridRetriever(repository, embedder, candidate_k=candidate_k)

    def _resolve(self, requested: str | Path) -> tuple[Path, Path]:
        candidate = Path(requested).expanduser()
        matches = [root / candidate for root in self.allowed_roots] if not candidate.is_absolute() else [candidate]
        for path in matches:
            try:
                resolved = path.resolve(strict=True)
            except (FileNotFoundError, OSError):
                continue
            for root in self.allowed_roots:
                try:
                    resolved.relative_to(root)
                    return resolved, root
                except ValueError:
                    continue
        raise RagError("Path is missing or outside configured knowledge roots")

    def _source_key(self, path: Path, root: Path) -> str:
        root_label = root.name or "root"
        if sum(item.name == root.name for item in self.allowed_roots) > 1:
            root_label = f"{root_label}-{self.allowed_roots.index(root) + 1}"
        return f"{root_label}/{path.relative_to(root).as_posix()}"

    def index_path(self, requested: str | Path, user_id: str) -> dict[str, object]:
        resolved, root = self._resolve(requested)
        if resolved.is_dir():
            files = sorted(path for path in resolved.rglob("*") if path.is_file() and not path.is_symlink())
            if len(files) > 500:
                raise RagError("A single indexing request is limited to 500 files")
        elif resolved.is_file():
            files = [resolved]
        else:
            raise RagError("Only regular files and directories can be indexed")

        indexed: list[RagDocument] = []
        skipped: list[str] = []
        for path in files:
            source_path = self._source_key(path, root)
            if path.suffix.casefold() not in SUPPORTED_SUFFIXES or path.stat().st_size > self.max_file_bytes:
                skipped.append(source_path)
                continue
            try:
                raw = path.read_bytes()
                loaded = load_document(path)
                chunks = chunk_document(loaded.segments, self.chunk_chars, self.overlap_chars)
                if not chunks:
                    logger.info("RAG source has no extractable text: %s", source_path)
                    skipped.append(source_path)
                    continue
                embedding_texts = [
                    f"{chunk.metadata.get('section', '')}\n{chunk.text}".strip() for chunk in chunks
                ]
                vectors = self.embedder.embed_documents(embedding_texts)
                if len(vectors) != len(chunks):
                    raise RagError("The local embedder returned an unexpected number of vectors")
                ready_chunks = [replace(chunk, embedding=vector)
                                for chunk, vector in zip(chunks, vectors, strict=True)]
                indexed.append(self.repository.replace_document(
                    user_id, source_path, loaded.name, hashlib.sha256(raw).hexdigest(), ready_chunks,
                ))
            except (DocumentLoadError, OSError, UnicodeError, ValueError) as exc:
                logger.warning("RAG source skipped: %s (%s)", source_path, type(exc).__name__)
                skipped.append(source_path)
        logger.info("RAG indexing finished: indexed=%d skipped=%d", len(indexed), len(skipped))
        return {"indexed": indexed, "skipped": skipped}

    def search(self, query: str, user_id: str, top_k: int | None = None):
        return self.retriever.search(query, user_id, top_k or self.top_k)

    def list_documents(self, user_id: str) -> list[RagDocument]:
        return self.repository.list_documents(user_id)

    def delete_document(self, document_id: str, user_id: str) -> bool:
        return self.repository.delete_document(document_id, user_id)

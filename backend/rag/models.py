"""Records shared by local RAG ingestion, storage, retrieval, and API layers."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DocumentSegment:
    text: str
    page_number: int | None = None
    location_unit: str = "line"
    section: str | None = None
    start_line: int = 1


@dataclass(frozen=True)
class LoadedDocument:
    name: str
    segments: list[DocumentSegment]


@dataclass(frozen=True)
class RagChunkInput:
    text: str
    page_number: int | None
    line_start: int | None
    line_end: int | None
    metadata: dict[str, object]
    embedding: list[float]


@dataclass(frozen=True)
class RagDocument:
    id: str
    user_id: str
    source_path: str
    document_name: str
    content_hash: str
    updated_at: datetime
    chunk_count: int


@dataclass(frozen=True)
class RagChunk:
    id: int
    document_id: str
    source_path: str
    document_name: str
    text: str
    page_number: int | None
    line_start: int | None
    line_end: int | None
    metadata: dict[str, object]

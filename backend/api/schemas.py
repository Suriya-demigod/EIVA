"""Public request and response contracts for the EIVA API."""

from typing import Literal
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(APIModel):
    message: str = Field(min_length=1, max_length=16_000)
    conversation_id: UUID | None = None
    task_id: UUID | None = None
    stream: bool = False


class ChatMessage(APIModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatResponse(APIModel):
    conversation_id: UUID
    task_id: UUID | None = None
    request_id: UUID
    model: str
    message: ChatMessage
    context_truncated: bool
    estimated_input_tokens: int
    system_prompt_version: str


class ErrorDetail(APIModel):
    code: str
    message: str
    request_id: UUID
    details: list[dict[str, object]] | None = None


class ErrorResponse(APIModel):
    error: ErrorDetail


class AgentSummary(APIModel):
    name: str
    status: Literal["planned", "registered"] = "planned"
    description: str
    model_role: str


class AgentListResponse(APIModel):
    items: list[AgentSummary]


class TaskSummary(APIModel):
    id: UUID
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    description: str
    workflow: Literal["research", "coding"]
    progress_percent: int = Field(ge=0, le=100)
    error: str | None = None
    created_at: datetime | None = None


class ToolCallRequest(APIModel):
    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, object] = Field(default_factory=dict)
    approval_id: str | None = Field(default=None, min_length=1, max_length=256)


class TaskCreateRequest(APIModel):
    description: str = Field(min_length=1, max_length=16_000)
    workflow: Literal["research", "coding"] = "research"
    tool_calls: list[ToolCallRequest] = Field(default_factory=list, max_length=8)


class TaskDetailResponse(TaskSummary):
    request_id: UUID
    result: dict[str, object] | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskCheckpointSummary(APIModel):
    id: UUID
    task_id: UUID
    name: str
    payload: dict[str, object]
    created_at: datetime


class MemoryCreateRequest(APIModel):
    content: str = Field(min_length=1, max_length=16_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    importance: int = Field(default=3, ge=1, le=5)
    source_conversation_id: UUID | None = None
    source_task_id: UUID | None = None


class MemorySummary(APIModel):
    id: UUID
    content: str
    tags: list[str]
    importance: int
    source_conversation_id: UUID | None = None
    source_task_id: UUID | None = None
    created_at: datetime


class MemoryListResponse(APIModel):
    items: list[MemorySummary]


class TaskListResponse(APIModel):
    items: list[TaskSummary]


class ApprovalSummary(APIModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    task_id: UUID
    request_id: UUID
    tool_name: str
    summary: str
    status: Literal["pending", "approved", "denied", "cancelled"]
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalListResponse(APIModel):
    items: list[ApprovalSummary]


class KnowledgeIndexRequest(APIModel):
    path: str = Field(min_length=1, max_length=1_000)


class KnowledgeSearchRequest(APIModel):
    query: str = Field(min_length=1, max_length=2_000)
    limit: int | None = Field(default=None, ge=5, le=8)


class KnowledgeDeleteResponse(APIModel):
    deleted: bool


class KnowledgeSourceSummary(APIModel):
    id: UUID
    source_path: str
    document_name: str
    content_hash: str
    updated_at: datetime
    chunk_count: int


class KnowledgeIndexResponse(APIModel):
    indexed: list[KnowledgeSourceSummary]
    skipped: list[str]


class KnowledgeCitation(APIModel):
    label: str
    source_id: UUID
    source_path: str
    document_name: str
    page_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    location: str | None = None
    section: str | None = None


class KnowledgeHit(KnowledgeCitation):
    text: str
    score: float


class KnowledgeSearchResponse(APIModel):
    items: list[KnowledgeHit]


class KnowledgeAnswerRequest(KnowledgeSearchRequest):
    pass


class KnowledgeAnswerResponse(APIModel):
    answer: str
    model: str | None = None
    citations: list[KnowledgeCitation]


class VisionAnalyzeResponse(APIModel):
    answer: str
    model: str
    request_id: UUID


class VisionScreenRequest(APIModel):
    task_id: UUID
    question: str = Field(min_length=1, max_length=4_000)

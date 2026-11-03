"""Validated storage records shared by SQLite repositories."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class StorageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryRecord(StorageModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=16_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    importance: int = Field(default=3, ge=1, le=5)
    source_conversation_id: UUID | None = None
    source_task_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskCheckpointRecord(StorageModel):
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    name: str = Field(min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

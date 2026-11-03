"""Shared agent types, lifecycle context, and progress events."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentDefinition(AgentModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", min_length=2, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    model_role: str = Field(min_length=1, max_length=64)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    skills: list[str] = Field(default_factory=list)


class AgentInput(AgentModel):
    task: str = Field(min_length=1, max_length=16_000)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(AgentModel):
    message: str = Field(min_length=1, max_length=32_000)
    data: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(AgentModel):
    event_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    request_id: UUID
    agent_name: str
    kind: Literal["started", "progress", "completed", "failed", "cancelled"]
    message: str = Field(min_length=1, max_length=500)
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


AgentEventSink = Callable[[AgentEvent], Awaitable[None] | None]


class AgentContext:
    def __init__(
        self,
        *,
        task_id: UUID,
        request_id: UUID,
        agent_name: str,
        cancellation_event: asyncio.Event,
        report_progress: Callable[[str, int | None], Awaitable[None]],
    ) -> None:
        self.task_id = task_id
        self.request_id = request_id
        self.agent_name = agent_name
        self._cancellation_event = cancellation_event
        self._report_progress = report_progress

    @property
    def cancellation_requested(self) -> bool:
        return self._cancellation_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancellation_requested:
            raise asyncio.CancelledError

    async def report_progress(self, message: str, progress_percent: int | None = None) -> None:
        self.raise_if_cancelled()
        await self._report_progress(message, progress_percent)


class BaseAgent(ABC):
    """Common asynchronous contract implemented by every EIVA agent."""

    def __init__(self, definition: AgentDefinition) -> None:
        self.definition = definition

    @abstractmethod
    async def run(self, payload: AgentInput, context: AgentContext) -> AgentOutput:
        """Execute one typed task and return a typed result."""

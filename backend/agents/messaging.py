"""Validated, bounded, task-scoped internal agent messages."""

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    request_id: UUID
    sender: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    recipient: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    kind: Literal["request", "response", "progress", "failure"]
    content: str = Field(min_length=1, max_length=16_000)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentMessageBus:
    """Publish messages only within an explicit task scope."""

    def __init__(self, history_limit: int = 100, queue_limit: int = 50) -> None:
        self._history_limit = history_limit
        self._queue_limit = queue_limit
        self._history: dict[UUID, deque[AgentMessage]] = defaultdict(lambda: deque(maxlen=history_limit))
        self._subscribers: dict[UUID, set[asyncio.Queue[AgentMessage]]] = defaultdict(set)

    def publish(self, message: AgentMessage) -> AgentMessage:
        message = AgentMessage.model_validate(message)
        self._history[message.task_id].append(message)
        for queue in tuple(self._subscribers.get(message.task_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(message)
        return message

    def history(self, task_id: UUID) -> list[AgentMessage]:
        return [message.model_copy(deep=True) for message in self._history.get(task_id, ())]

    def subscribe(self, task_id: UUID) -> tuple[list[AgentMessage], asyncio.Queue[AgentMessage]]:
        queue: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=self._queue_limit)
        self._subscribers[task_id].add(queue)
        return self.history(task_id), queue

    def unsubscribe(self, task_id: UUID, queue: asyncio.Queue[AgentMessage]) -> None:
        subscribers = self._subscribers.get(task_id)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(task_id, None)

    def discard(self, task_id: UUID) -> None:
        if task_id not in self._subscribers:
            self._history.pop(task_id, None)

"""Bounded per-task event history with replayable live subscriptions."""

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    sequence: int = Field(ge=1)
    kind: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskEventBus:
    def __init__(
        self,
        *,
        history_limit: int = 200,
        subscriber_queue_size: int = 100,
        persist_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._history_limit = history_limit
        self._subscriber_queue_size = subscriber_queue_size
        self._events: dict[UUID, deque[TaskEvent]] = defaultdict(lambda: deque(maxlen=self._history_limit))
        self._sequences: dict[UUID, int] = defaultdict(int)
        self._subscribers: dict[UUID, set[asyncio.Queue[TaskEvent]]] = defaultdict(set)
        self._persist_event = persist_event

    def publish(self, task_id: UUID, kind: str, payload: dict[str, Any] | None = None) -> TaskEvent:
        sequence = self._sequences[task_id] + 1
        self._sequences[task_id] = sequence
        event = TaskEvent(task_id=task_id, sequence=sequence, kind=kind, payload=payload or {})
        self._events[task_id].append(event)
        if self._persist_event is not None:
            self._persist_event(event.model_dump(mode="json"))
        for queue in tuple(self._subscribers.get(task_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
        return event

    def restore(self, event_data: list[dict[str, Any]]) -> None:
        for item in event_data:
            event = TaskEvent.model_validate(item)
            self._events[event.task_id].append(event)
            self._sequences[event.task_id] = max(self._sequences[event.task_id], event.sequence)

    def history(self, task_id: UUID, after_sequence: int = 0) -> list[TaskEvent]:
        return [event for event in self._events.get(task_id, ()) if event.sequence > after_sequence]

    def subscribe(self, task_id: UUID, after_sequence: int = 0) -> tuple[list[TaskEvent], asyncio.Queue[TaskEvent]]:
        replay = self.history(task_id, after_sequence)
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        self._subscribers[task_id].add(queue)
        return replay, queue

    def unsubscribe(self, task_id: UUID, queue: asyncio.Queue[TaskEvent]) -> None:
        subscribers = self._subscribers.get(task_id)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(task_id, None)

    def discard(self, task_id: UUID) -> None:
        if task_id in self._subscribers:
            return
        self._events.pop(task_id, None)
        self._sequences.pop(task_id, None)

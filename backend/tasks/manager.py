"""Bounded in-memory task records with validated lifecycle transitions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.database.models import TaskCheckpointRecord
from backend.database.repositories import TaskRepository
from backend.orchestration.events import TaskEventBus


class TaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


TERMINAL_STATUSES = {TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled}
ALLOWED_TRANSITIONS = {
    TaskStatus.queued: {TaskStatus.running, TaskStatus.failed, TaskStatus.cancelled},
    TaskStatus.running: {TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled},
    TaskStatus.completed: set(),
    TaskStatus.failed: set(),
    TaskStatus.cancelled: set(),
}


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    workflow: str
    status: TaskStatus = TaskStatus.queued
    description: str
    progress_percent: int = Field(default=0, ge=0, le=100)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class InvalidTaskTransition(ValueError):
    pass


class TaskNotFound(LookupError):
    pass


class TaskCapacityExceeded(RuntimeError):
    pass


TaskRunner = Callable[[UUID, UUID], Awaitable[None]]


class TaskManager:
    def __init__(
        self,
        event_bus: TaskEventBus,
        *,
        max_records: int = 500,
        repository: TaskRepository | None = None,
    ) -> None:
        self.events = event_bus
        self._max_records = max_records
        self._repository = repository
        self._records: dict[UUID, TaskRecord] = {}
        self._jobs: dict[UUID, asyncio.Task[None]] = {}
        if repository is not None:
            records = reversed(repository.list_tasks(max_records))
            for data in records:
                record = TaskRecord.model_validate(data)
                self._records[record.id] = record
                event_bus.restore(repository.list_events(record.id))
                if record.status not in TERMINAL_STATUSES:
                    record.status = TaskStatus.failed
                    record.error = "Task interrupted by application restart"
                    record.completed_at = datetime.now(timezone.utc)
                    repository.save_task(record.model_dump(mode="json"))
                    event_bus.publish(record.id, "task.failed", self._public(record) | {"error": record.error})

    async def shutdown(self) -> None:
        jobs = list(self._jobs.items())
        for task_id, job in jobs:
            record = self._records.get(task_id)
            if record and record.status not in TERMINAL_STATUSES:
                job.cancel()
                if record.status == TaskStatus.queued:
                    self.transition(task_id, TaskStatus.cancelled, error="Application is shutting down")
        if jobs:
            await asyncio.gather(*(job for _, job in jobs), return_exceptions=True)

    def create(self, workflow: str, description: str, request_id: UUID, runner: TaskRunner) -> TaskRecord:
        self._make_room()
        record = TaskRecord(workflow=workflow, description=description, request_id=request_id)
        self._records[record.id] = record
        if self._repository is not None:
            self._repository.save_task(record.model_dump(mode="json"))
        self.events.publish(record.id, "task.queued", self._public(record))
        job = asyncio.create_task(runner(record.id, request_id), name=f"eiva-task:{record.id}")
        self._jobs[record.id] = job
        job.add_done_callback(lambda _: self._jobs.pop(record.id, None))
        return record

    def _make_room(self) -> None:
        if len(self._records) < self._max_records:
            return
        for task_id, record in tuple(self._records.items()):
            if record.status in TERMINAL_STATUSES:
                self._records.pop(task_id, None)
                self.events.discard(task_id)
                if self._repository is not None:
                    self._repository.delete_task(task_id)
                if len(self._records) < self._max_records:
                    return
        raise TaskCapacityExceeded("Task history is full while all retained tasks are active")

    @staticmethod
    def _public(record: TaskRecord) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "workflow": record.workflow,
            "status": record.status.value,
            "description": record.description,
            "progress_percent": record.progress_percent,
        }

    def get(self, task_id: UUID) -> TaskRecord:
        try:
            return self._records[task_id]
        except KeyError as exc:
            raise TaskNotFound(f"Task '{task_id}' was not found") from exc

    def list(self) -> list[TaskRecord]:
        return list(reversed(self._records.values()))

    def transition(self, task_id: UUID, status: TaskStatus, *, error: str | None = None) -> TaskRecord:
        record = self.get(task_id)
        if status not in ALLOWED_TRANSITIONS[record.status]:
            raise InvalidTaskTransition(f"Cannot transition task from {record.status.value} to {status.value}")
        now = datetime.now(timezone.utc)
        record.status = status
        record.error = error
        if status == TaskStatus.running:
            record.started_at = now
        if status in TERMINAL_STATUSES:
            record.completed_at = now
            if status == TaskStatus.completed:
                record.progress_percent = 100
        if self._repository is not None:
            self._repository.save_task(record.model_dump(mode="json"))
        self.events.publish(task_id, f"task.{status.value}", self._public(record) | ({"error": error} if error else {}))
        return record

    def update_progress(self, task_id: UUID, percent: int, message: str) -> TaskRecord:
        record = self.get(task_id)
        if record.status != TaskStatus.running:
            raise InvalidTaskTransition("Progress can only be updated while a task is running")
        if percent < record.progress_percent or not 0 <= percent <= 99:
            raise ValueError("Progress must be monotonic and below 100 until completion")
        record.progress_percent = percent
        if self._repository is not None:
            self._repository.save_task(record.model_dump(mode="json"))
        self.events.publish(task_id, "task.progress", {"progress_percent": percent, "message": message})
        return record

    def set_result(self, task_id: UUID, result: dict[str, Any]) -> TaskRecord:
        record = self.get(task_id)
        if record.status != TaskStatus.running:
            raise InvalidTaskTransition("Results can only be attached to a running task")
        record.result = result
        if self._repository is not None:
            self._repository.save_task(record.model_dump(mode="json"))
        return record

    def checkpoint(self, task_id: UUID, name: str, payload: dict[str, Any]) -> TaskCheckpointRecord:
        self.get(task_id)
        checkpoint = TaskCheckpointRecord(task_id=task_id, name=name, payload=payload)
        if self._repository is not None:
            self._repository.save_checkpoint(checkpoint)
        self.events.publish(task_id, "task.checkpoint", {"checkpoint_id": str(checkpoint.id), "name": name})
        return checkpoint

    def checkpoints(self, task_id: UUID) -> list[TaskCheckpointRecord]:
        self.get(task_id)
        return self._repository.list_checkpoints(task_id) if self._repository is not None else []

    def cancel(self, task_id: UUID) -> TaskRecord:
        record = self.get(task_id)
        if record.status in TERMINAL_STATUSES:
            return record
        job = self._jobs.get(task_id)
        if job is not None:
            job.cancel()
        if record.status == TaskStatus.queued:
            self.transition(task_id, TaskStatus.cancelled, error="Task cancelled before execution")
        return self.get(task_id)


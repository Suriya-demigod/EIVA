"""Task submission, inspection, cancellation, and live event streaming."""

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.api.schemas import (
    TaskCreateRequest,
    TaskCheckpointSummary,
    TaskDetailResponse,
    TaskListResponse,
    TaskSummary,
)
from backend.orchestration.events import TaskEvent
from backend.orchestration.graph import ToolRequest
from backend.orchestration.supervisor import WorkflowSupervisor
from backend.tasks.manager import TaskCapacityExceeded, TaskNotFound, TaskRecord, TaskStatus, TERMINAL_STATUSES

router = APIRouter(prefix="/tasks", tags=["tasks"])
TERMINAL_EVENTS = {"task.completed", "task.failed", "task.cancelled"}


def _supervisor(request: Request) -> WorkflowSupervisor:
    return request.app.state.supervisor


def _summary(record: TaskRecord) -> TaskSummary:
    return TaskSummary(
        id=record.id,
        status=record.status.value,
        description=record.description,
        workflow=record.workflow,
        progress_percent=record.progress_percent,
        error=record.error,
        created_at=record.created_at,
    )


def _detail(record: TaskRecord) -> TaskDetailResponse:
    return TaskDetailResponse(
        **_summary(record).model_dump(),
        request_id=record.request_id,
        result=record.result,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


@router.post("", response_model=TaskDetailResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(payload: TaskCreateRequest, request: Request) -> TaskDetailResponse:
    supervisor = _supervisor(request)
    try:
        record = supervisor.submit(
            workflow=payload.workflow,
            description=payload.description,
            tool_requests=[
                ToolRequest(name=call.name, arguments=call.arguments, approval_id=call.approval_id)
                for call in payload.tool_calls
            ],
            request_id=request.state.request_id,
        )
    except TaskCapacityExceeded as exc:
        raise HTTPException(status_code=503, detail="Task capacity is full; retry after active tasks finish") from exc
    return _detail(record)


@router.get("", response_model=TaskListResponse)
async def list_tasks(request: Request) -> TaskListResponse:
    manager = _supervisor(request).tasks
    return TaskListResponse(items=[_summary(record) for record in manager.list()])


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: UUID, request: Request) -> TaskDetailResponse:
    try:
        return _detail(_supervisor(request).tasks.get(task_id))
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail="Task was not found") from exc


@router.post("/{task_id}/cancel", response_model=TaskDetailResponse, status_code=status.HTTP_202_ACCEPTED)
async def cancel_task(task_id: UUID, request: Request) -> TaskDetailResponse:
    try:
        return _detail(_supervisor(request).tasks.cancel(task_id))
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail="Task was not found") from exc


@router.get("/{task_id}/events")
async def stream_task_events(
    task_id: UUID,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
):
    supervisor = _supervisor(request)
    try:
        record = supervisor.tasks.get(task_id)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail="Task was not found") from exc

    async def generate():
        replay, queue = supervisor.events.subscribe(task_id, after_sequence)
        try:
            for event in replay:
                yield _sse(event)
                if event.kind in TERMINAL_EVENTS:
                    return
            if record.status in TERMINAL_STATUSES:
                return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event)
                if event.kind in TERMINAL_EVENTS:
                    return
        finally:
            supervisor.events.unsubscribe(task_id, queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{task_id}/checkpoints", response_model=list[TaskCheckpointSummary])
async def list_task_checkpoints(task_id: UUID, request: Request) -> list[TaskCheckpointSummary]:
    try:
        records = _supervisor(request).tasks.checkpoints(task_id)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail="Task was not found") from exc
    return [
        TaskCheckpointSummary(
            id=record.id,
            task_id=record.task_id,
            name=record.name,
            payload=record.payload,
            created_at=record.created_at,
        )
        for record in records
    ]


def _sse(event: TaskEvent) -> str:
    data: dict[str, Any] = event.model_dump(mode="json")
    return f"id: {event.sequence}\nevent: {event.kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

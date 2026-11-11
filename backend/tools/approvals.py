"""In-process, task-scoped approval requests for consequential tool calls."""

from collections import OrderedDict
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    cancelled = "cancelled"


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    task_id: UUID
    request_id: UUID
    tool_name: str
    summary: str
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalNotFound(LookupError):
    pass


class ApprovalAlreadyDecided(ValueError):
    pass


class ApprovalCapacityExceeded(RuntimeError):
    pass


class _ApprovalWaiter:
    def __init__(self, record: ApprovalRecord) -> None:
        import asyncio

        self.record = record
        self.event = asyncio.Event()


class ApprovalManager:
    """Keep pending decisions local and expose only safe action summaries."""

    def __init__(self, max_records: int = 512) -> None:
        self._max_records = max_records
        self._records: OrderedDict[UUID, _ApprovalWaiter] = OrderedDict()

    def request(self, tool_name: str, task_id: UUID, request_id: UUID, summary: str) -> ApprovalRecord:
        self._make_room()
        now = datetime.now(timezone.utc)
        record = ApprovalRecord(
            id=uuid4(),
            task_id=task_id,
            request_id=request_id,
            tool_name=tool_name,
            summary=summary,
            status=ApprovalStatus.pending,
            created_at=now,
        )
        self._records[record.id] = _ApprovalWaiter(record)
        return record.model_copy(deep=True)

    async def wait(self, approval_id: UUID) -> ApprovalRecord:
        waiter = self._get(approval_id)
        await waiter.event.wait()
        return waiter.record.model_copy(deep=True)

    def decide(self, approval_id: UUID, approved: bool) -> ApprovalRecord:
        waiter = self._get(approval_id)
        if waiter.record.status != ApprovalStatus.pending:
            raise ApprovalAlreadyDecided("Approval request is no longer pending")
        waiter.record.status = ApprovalStatus.approved if approved else ApprovalStatus.denied
        waiter.record.decided_at = datetime.now(timezone.utc)
        waiter.event.set()
        return waiter.record.model_copy(deep=True)

    def pending(self) -> list[ApprovalRecord]:
        return [
            waiter.record.model_copy(deep=True)
            for waiter in reversed(self._records.values())
            if waiter.record.status == ApprovalStatus.pending
        ]

    def cancel_task(self, task_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        for waiter in self._records.values():
            if waiter.record.task_id == task_id and waiter.record.status == ApprovalStatus.pending:
                waiter.record.status = ApprovalStatus.cancelled
                waiter.record.decided_at = now
                waiter.event.set()

    def cancel_all(self) -> None:
        now = datetime.now(timezone.utc)
        for waiter in self._records.values():
            if waiter.record.status == ApprovalStatus.pending:
                waiter.record.status = ApprovalStatus.cancelled
                waiter.record.decided_at = now
                waiter.event.set()

    def _get(self, approval_id: UUID) -> _ApprovalWaiter:
        waiter = self._records.get(approval_id)
        if waiter is None:
            raise ApprovalNotFound("Approval request was not found")
        return waiter

    def _make_room(self) -> None:
        while len(self._records) >= self._max_records:
            finished_id = next(
                (
                    approval_id
                    for approval_id, waiter in self._records.items()
                    if waiter.record.status != ApprovalStatus.pending
                ),
                None,
            )
            if finished_id is None:
                raise ApprovalCapacityExceeded("The pending approval queue is full")
            self._records.pop(finished_id)

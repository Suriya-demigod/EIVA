"""Local approval queue for task-scoped consequential tool actions."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.api.schemas import ApprovalListResponse, ApprovalSummary
from backend.tools.approvals import ApprovalAlreadyDecided, ApprovalNotFound

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool


@router.get("", response_model=ApprovalListResponse)
async def list_pending_approvals(request: Request) -> ApprovalListResponse:
    manager = request.app.state.approval_manager
    return ApprovalListResponse(items=[ApprovalSummary.model_validate(item) for item in manager.pending()])


@router.post("/{approval_id}", response_model=ApprovalSummary)
async def decide_approval(approval_id: UUID, payload: ApprovalDecision, request: Request) -> ApprovalSummary:
    manager = request.app.state.approval_manager
    try:
        record = manager.decide(approval_id, payload.approved)
    except ApprovalNotFound as exc:
        raise HTTPException(status_code=404, detail="Approval request was not found") from exc
    except ApprovalAlreadyDecided as exc:
        raise HTTPException(status_code=409, detail="Approval request is no longer pending") from exc
    request.app.state.event_bus.publish(
        record.task_id,
        "approval.decided",
        {"approval_id": str(record.id), "status": record.status.value},
    )
    return ApprovalSummary.model_validate(record)

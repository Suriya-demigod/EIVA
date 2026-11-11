"""Opt-in A2A 1.0 HTTP+JSON server and authenticated local dispatch endpoint."""

import hmac
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from backend.agents.messaging import AgentMessage
from backend.config import get_settings
from backend.tasks.manager import TaskNotFound, TaskStatus

router = APIRouter(tags=["agent communication"])
TASK_STATES = {
    TaskStatus.queued: "TASK_STATE_SUBMITTED",
    TaskStatus.running: "TASK_STATE_WORKING",
    TaskStatus.completed: "TASK_STATE_COMPLETED",
    TaskStatus.failed: "TASK_STATE_FAILED",
    TaskStatus.cancelled: "TASK_STATE_CANCELED",
}


class A2APart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4_000)


class A2AMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["ROLE_USER"]
    parts: list[A2APart] = Field(min_length=1, max_length=8)
    messageId: str | None = Field(default=None, min_length=1, max_length=128)
    taskId: str | None = Field(default=None, min_length=1, max_length=128)
    contextId: str | None = Field(default=None, min_length=1, max_length=128)


class A2ASendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: A2AMessage
    configuration: dict[str, object] | None = None


class AgentDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    peer: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", min_length=2, max_length=64)
    message: str = Field(min_length=1, max_length=4_000)


def _require_enabled() -> str:
    settings = get_settings()
    if not settings.a2a_enabled:
        raise HTTPException(status_code=404, detail="A2A communication is disabled")
    if settings.a2a_server_token is None:
        raise HTTPException(status_code=503, detail="A2A server authentication is not configured")
    return settings.a2a_server_token.get_secret_value()


def _authorize(request: Request) -> None:
    expected = _require_enabled()
    provided = request.headers.get("authorization", "")
    scheme, _, token = provided.partition(" ")
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="A2A bearer authentication failed", headers={"WWW-Authenticate": "Bearer"})


@router.get("/.well-known/agent-card.json", include_in_schema=False)
async def agent_card() -> JSONResponse:
    settings = get_settings()
    if not settings.a2a_enabled:
        raise HTTPException(status_code=404, detail="A2A communication is disabled")
    endpoint = settings.a2a_public_url.rstrip("/")
    return JSONResponse(
        {
            "name": settings.a2a_agent_name,
            "description": settings.a2a_agent_description,
            "supportedInterfaces": [
                {"url": endpoint, "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}
            ],
            "version": "0.1.0",
            "capabilities": {"streaming": False, "pushNotifications": False},
            "securitySchemes": {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
            "securityRequirements": [{"schemes": {"bearer": []}}],
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": [
                {"id": "research", "name": "Research", "description": "Run a scoped EIVA research workflow", "tags": ["research"]},
                {"id": "coding", "name": "Coding", "description": "Run a scoped EIVA coding workflow", "tags": ["coding"]},
            ],
        },
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.post("/a2a/v1/message:send", include_in_schema=False, dependencies=[Depends(_require_enabled)])
async def receive_message(payload: A2ASendRequest, request: Request) -> JSONResponse:
    _authorize(request)
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/a2a+json", "application/json"}:
        raise HTTPException(status_code=415, detail="A2A requests must use application/a2a+json")
    if payload.message.taskId is not None:
        raise HTTPException(status_code=501, detail="A2A follow-up messages are not supported yet")
    text = "\n".join(part.text for part in payload.message.parts).strip()
    if not text or len(text) > 4_000:
        raise HTTPException(status_code=422, detail="A2A message text is empty or too large")
    supervisor = request.app.state.supervisor
    task = supervisor.submit(
        workflow="research",
        description=text,
        tool_requests=[],
        request_id=request.state.request_id,
    )
    request.app.state.agent_message_bus.publish(
        AgentMessage(
            task_id=task.id,
            request_id=request.state.request_id,
            sender="a2a_peer",
            recipient="researcher",
            kind="request",
            content=text,
            metadata={"protocol": "a2a/1.0", "message_id": payload.message.messageId},
        )
    )
    request.app.state.event_bus.publish(
        task.id,
        "agent.message.received",
        {"protocol": "a2a/1.0", "message_id": payload.message.messageId},
    )
    return JSONResponse(
        {"task": {"id": str(task.id), "contextId": str(task.id), "status": {"state": TASK_STATES[task.status]}}},
        media_type="application/a2a+json",
    )


@router.get("/a2a/v1/tasks/{task_id}", include_in_schema=False, dependencies=[Depends(_require_enabled)])
async def get_remote_task(task_id: UUID, request: Request) -> JSONResponse:
    _authorize(request)
    try:
        task = request.app.state.supervisor.tasks.get(task_id)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail="A2A task was not found") from exc
    result = {"id": str(task.id), "contextId": str(task.id), "status": {"state": TASK_STATES[task.status]}}
    if task.error:
        result["status"]["message"] = {"role": "ROLE_AGENT", "parts": [{"text": task.error}]}
    if task.status == TaskStatus.completed and task.result:
        result["artifacts"] = [{"artifactId": str(task.id), "name": "result", "parts": [{"text": str(task.result.get("message", "Completed"))}]}]
    return JSONResponse({"task": result}, media_type="application/a2a+json")


@router.post("/api/v1/agent-messages", tags=["agent communication"])
async def dispatch_message(payload: AgentDispatchRequest, request: Request) -> dict:
    settings = get_settings()
    if not settings.a2a_enabled:
        raise HTTPException(status_code=503, detail="A2A communication is disabled")
    try:
        request.app.state.supervisor.tasks.get(payload.task_id)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail="Task was not found") from exc
    bus = request.app.state.agent_message_bus
    client = request.app.state.a2a_client
    message = AgentMessage(
        task_id=payload.task_id,
        request_id=request.state.request_id,
        sender="eiva",
        recipient=payload.peer,
        kind="request",
        content=payload.message,
        metadata={"protocol": "a2a/1.0"},
    )
    bus.publish(message)
    request.app.state.event_bus.publish(payload.task_id, "agent.message.sent", {"peer": payload.peer, "message_id": str(message.id)})
    try:
        result = await client.send_message(payload.peer, payload.message, str(message.id))
    except Exception as exc:
        bus.publish(message.model_copy(update={"kind": "failure", "content": "Remote agent communication failed"}))
        request.app.state.event_bus.publish(
            payload.task_id,
            "agent.message.failed",
            {"peer": payload.peer, "message_id": str(message.id), "error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=502, detail="Remote agent communication failed") from exc
    response_content = str(result.get("message") or result.get("task") or "Remote agent accepted the request")[:16_000]
    bus.publish(message.model_copy(update={"kind": "response", "content": response_content}))
    request.app.state.event_bus.publish(payload.task_id, "agent.message.received", {"peer": payload.peer, "message_id": str(message.id)})
    return {"message_id": str(message.id), "peer": payload.peer, "response": result}

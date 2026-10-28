"""Chat routes — non-streaming and SSE streaming."""
from __future__ import annotations

import logging
import json
import uuid
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.models.request_models import ChatRequest
from app.models.response_models import ChatResponse, ErrorResponse
from app.services import chat_service
from app.core.orchestrator import selected_model_id
from app.api.errors import provider_http_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


def _session_id(request: Request) -> str:
    session_id = request.headers.get("X-Session-Id") or str(uuid.uuid4())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(status_code=400, detail="Invalid X-Session-Id header.")
    return session_id


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={500: {"model": ErrorResponse}},
)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    """Handle a chat request (non-streaming or streaming)."""
    session_id = _session_id(request)
    user_msg = req.messages[-1].content

    if req.stream:
        raise HTTPException(400, "Use /api/chat/stream for streaming requests.")

    try:
        reply = await chat_service.chat(session_id, user_msg)
        return ChatResponse(
            reply=reply,
            model=selected_model_id(user_msg),
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.exception("Chat request failed")
        raise provider_http_error(exc) from exc


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """SSE streaming endpoint."""
    session_id = _session_id(request)
    user_msg = req.messages[-1].content

    async def event_generator():
        try:
            async for chunk in chat_service.chat_stream(session_id, user_msg):
                yield _sse({"type": "delta", "text": chunk})
            yield _sse({"type": "done"})
        except Exception as exc:
            logger.exception("Stream error")
            error = provider_http_error(exc)
            yield _sse({"type": "error", "message": error.detail})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

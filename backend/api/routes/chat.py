"""Chat endpoint with scoped, bounded conversation context."""

import json
import logging
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from groq import GroqError, RateLimitError

from backend.api.schemas import ChatMessage, ChatRequest, ChatResponse
from backend.config import get_settings
from backend.core.context_builder import ContextBuilder, ContextWindowExceeded
from backend.core.model_router import ModelRouter, completion_text, get_model_router
from backend.memory.short_term import (
    ContextScope,
    ConversationCapacityExceeded,
    ShortTermMemory,
    get_short_term_memory,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("eiva.streaming")


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_context(
    scope: ContextScope,
    payload: ChatRequest,
    memory: ShortTermMemory,
    builder: ContextBuilder,
):
    return builder.build(
        memory.get_history(scope),
        payload.message,
        history_was_truncated=memory.history_was_truncated(scope),
    )


@router.post(
    "",
    response_model=ChatResponse,
    summary="Send a message in a conversation",
    description=(
        "Sends one message with bounded history for this conversation and optional task. "
        "History is scoped to the configured local user and stored in SQLite. Set `stream` to true for "
        "Server-Sent Events (`token`, `done`, or `error`)."
    ),
    responses={
        200: {
            "description": "JSON chat response, or an event stream when `stream` is true.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        413: {"description": "Current message exceeds the configured context input budget."},
    },
)
async def chat(
    payload: ChatRequest,
    request: Request,
    model_router: ModelRouter = Depends(get_model_router),
    memory: ShortTermMemory = Depends(get_short_term_memory),
):
    settings = get_settings()
    conversation_id: UUID = payload.conversation_id or uuid4()
    request_id: UUID = request.state.request_id
    scope = ContextScope(
        user_id=settings.local_user_id,
        conversation_id=conversation_id,
        task_id=payload.task_id,
    )
    try:
        conversation_lock = memory.lock_for(scope)
    except ConversationCapacityExceeded as exc:
        raise HTTPException(
            status_code=503,
            detail="EIVA has reached its active conversation capacity; retry shortly",
        ) from exc
    builder = ContextBuilder(settings.context_max_input_tokens)
    model = model_router.model_for("chat")

    if payload.stream:
        async def events():
            started = time.perf_counter()
            first_delta_ms = None
            chunk_count = 0
            answer_parts: list[str] = []
            async with conversation_lock:
                try:
                    context = _build_context(scope, payload, memory, builder)
                except ContextWindowExceeded:
                    yield _event(
                        "error",
                        {
                            "code": "context_window_exceeded",
                            "message": "This message is too large for EIVA's configured context limit",
                            "request_id": str(request_id),
                        },
                    )
                    return

                try:
                    stream = await model_router.complete(
                        "chat",
                        context.messages,
                        request_id=request_id,
                        max_completion_tokens=settings.context_max_completion_tokens,
                        stream=True,
                    )
                    async for chunk in stream:
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if delta:
                            if first_delta_ms is None:
                                first_delta_ms = round((time.perf_counter() - started) * 1000)
                            chunk_count += 1
                            answer_parts.append(delta)
                            yield _event(
                                "token",
                                {
                                    "conversation_id": str(conversation_id),
                                    "task_id": str(payload.task_id) if payload.task_id else None,
                                    "request_id": str(request_id),
                                    "delta": delta,
                                },
                            )

                    answer = "".join(answer_parts)
                    memory.append_exchange(scope, payload.message, answer)
                    yield _event(
                        "done",
                        {
                            "conversation_id": str(conversation_id),
                            "task_id": str(payload.task_id) if payload.task_id else None,
                            "request_id": str(request_id),
                            "model": model,
                            "context_truncated": context.history_truncated,
                            "estimated_input_tokens": context.estimated_input_tokens,
                            "system_prompt_version": context.system_prompt_version,
                        },
                    )
                    logger.info(
                        "EIVA_MODEL_STREAM %s",
                        json.dumps(
                            {
                                "event": "completed",
                                "model": model,
                                "request_id": str(request_id),
                                "time_to_first_delta_ms": first_delta_ms,
                                "duration_ms": round((time.perf_counter() - started) * 1000),
                                "delta_count": chunk_count,
                                "estimated_input_tokens": context.estimated_input_tokens,
                                "context_truncated": context.history_truncated,
                            },
                            sort_keys=True,
                        ),
                    )
                except GroqError as exc:
                    code = "provider_rate_limited" if isinstance(exc, RateLimitError) else "provider_unavailable"
                    message = (
                        "The model provider is rate limiting requests"
                        if code == "provider_rate_limited"
                        else "The model provider could not complete the request"
                    )
                    logger.warning(
                        "EIVA_MODEL_STREAM %s",
                        json.dumps(
                            {
                                "event": "failed",
                                "model": model,
                                "request_id": str(request_id),
                                "duration_ms": round((time.perf_counter() - started) * 1000),
                                "error_type": type(exc).__name__,
                            },
                            sort_keys=True,
                        ),
                    )
                    yield _event(
                        "error",
                        {"code": code, "message": message, "request_id": str(request_id)},
                    )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async with conversation_lock:
        try:
            context = _build_context(scope, payload, memory, builder)
        except ContextWindowExceeded as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc

        completion = await model_router.complete(
            "chat",
            context.messages,
            request_id=request_id,
            max_completion_tokens=settings.context_max_completion_tokens,
        )
        content = completion_text(completion)
        memory.append_exchange(scope, payload.message, content)

    return ChatResponse(
        conversation_id=conversation_id,
        task_id=payload.task_id,
        request_id=request_id,
        model=completion.model or model,
        message=ChatMessage(content=content),
        context_truncated=context.history_truncated,
        estimated_input_tokens=context.estimated_input_tokens,
        system_prompt_version=context.system_prompt_version,
    )

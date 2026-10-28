"""Chat service — ties orchestrator and conversation history together."""
from __future__ import annotations

from typing import AsyncIterator

from app.core.orchestrator import handle_chat, handle_chat_stream
from app.services.conversation_service import conversation_service


async def chat(session_id: str, user_message: str) -> str:
    """Non-streaming chat."""
    conversation_service.add(session_id, "user", user_message)
    history = conversation_service.get(session_id)
    reply = await handle_chat(history)
    conversation_service.add(session_id, "assistant", reply)
    return reply


async def chat_stream(session_id: str, user_message: str) -> AsyncIterator[str]:
    """Streaming chat — yields text chunks."""
    conversation_service.add(session_id, "user", user_message)
    history = conversation_service.get(session_id)
    full_reply = []
    async for chunk in handle_chat_stream(history):
        full_reply.append(chunk)
        yield chunk
    conversation_service.add(session_id, "assistant", "".join(full_reply))

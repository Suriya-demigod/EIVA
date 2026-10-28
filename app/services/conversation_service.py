"""Conversation service — bounded in-memory history per session."""
from __future__ import annotations

from collections import OrderedDict
from app.core.config import get_settings


class ConversationService:
    """Stores conversation history keyed by session_id."""

    def __init__(self) -> None:
        self._store: OrderedDict[str, list[dict]] = OrderedDict()

    def add(self, session_id: str, role: str, content: str) -> None:
        history = self._store.setdefault(session_id, [])
        self._store.move_to_end(session_id)
        history.append({"role": role, "content": content})
        settings = get_settings()
        max_msgs = max(1, settings.max_history_messages)
        if len(history) > max_msgs:
            self._store[session_id] = history[-max_msgs:]
        while len(self._store) > max(1, settings.max_sessions):
            self._store.popitem(last=False)

    def get(self, session_id: str) -> list[dict]:
        history = self._store.get(session_id, [])
        if session_id in self._store:
            self._store.move_to_end(session_id)
        return list(history)

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)


# Singleton
conversation_service = ConversationService()

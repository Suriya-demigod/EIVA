"""Bounded recent context backed by the durable conversation repository."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Request

if TYPE_CHECKING:
    from backend.database.repositories import ConversationRepository


class ConversationCapacityExceeded(RuntimeError):
    """Raised when all tracked conversation slots are active."""


@dataclass(frozen=True)
class ContextScope:
    user_id: str
    conversation_id: UUID
    task_id: UUID | None = None


class ShortTermMemory:
    """Durable exchange store with per-scope locks and bounded prompt history."""

    def __init__(
        self,
        max_conversations: int = 512,
        max_history_messages: int = 80,
        repository: "ConversationRepository | None" = None,
    ) -> None:
        self._max_conversations = max_conversations
        self._max_history_messages = max_history_messages
        self._repository = repository
        self._history: OrderedDict[ContextScope, list[dict[str, str]]] = OrderedDict()
        self._truncated: set[ContextScope] = set()
        self._locks: dict[ContextScope, asyncio.Lock] = {}

    def _touch(self, scope: ContextScope) -> None:
        if scope in self._history:
            self._history.move_to_end(scope)
            return
        while len(self._history) >= self._max_conversations:
            evictable = next(
                (candidate for candidate in self._history if not self._locks[candidate].locked()),
                None,
            )
            if evictable is None:
                raise ConversationCapacityExceeded("All short-term conversation slots are active")
            self._history.pop(evictable)
            self._locks.pop(evictable, None)
        self._history[scope] = []
        self._locks.setdefault(scope, asyncio.Lock())

    def lock_for(self, scope: ContextScope) -> asyncio.Lock:
        self._touch(scope)
        self._history.move_to_end(scope)
        return self._locks[scope]

    def get_history(self, scope: ContextScope) -> list[dict[str, str]]:
        self._touch(scope)
        if self._repository is not None:
            return self._repository.get_history(scope)
        return [dict(item) for item in self._history[scope]]

    def history_was_truncated(self, scope: ContextScope) -> bool:
        self._touch(scope)
        return self._repository.was_truncated(scope) if self._repository is not None else scope in self._truncated

    def append_exchange(self, scope: ContextScope, user_message: str, assistant_message: str) -> None:
        self._touch(scope)
        if self._repository is not None:
            self._repository.append_exchange(scope, user_message, assistant_message, self._max_history_messages)
            return
        history = self._history[scope]
        history.extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": assistant_message}])
        while len(history) > self._max_history_messages:
            del history[:2]
            self._truncated.add(scope)


def get_short_term_memory(request: Request) -> ShortTermMemory:
    return request.app.state.short_term_memory

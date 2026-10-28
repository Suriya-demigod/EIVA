"""Abstract base agent."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from app.providers.base_provider import BaseProvider


class BaseAgent(ABC):
    """All agents share a provider and a default model id."""

    def __init__(self, provider: BaseProvider, model_id: str) -> None:
        self.provider = provider
        self.model_id = model_id

    @abstractmethod
    async def run(self, messages: list[dict], **kwargs: Any) -> str:
        """Process messages and return a response."""

    def prepare_messages(self, messages: list[dict]) -> list[dict]:
        """Add agent-specific instructions before a provider call."""
        return messages

    async def run_stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[str]:
        """Stream a response using the same prompt preparation as ``run``."""
        async for chunk in self.provider.chat_stream(
            self.prepare_messages(messages), self.model_id, **kwargs
        ):
            yield chunk

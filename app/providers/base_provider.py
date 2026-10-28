"""Abstract base for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


class BaseProvider(ABC):
    """Every provider must implement these two methods."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        """Return a complete chat response."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield text chunks as they arrive."""

    async def transcribe(
        self,
        audio: bytes,
        filename: str,
        content_type: str,
        *,
        language: str | None = None,
    ) -> str:
        """Convert an audio file to text when supported by the provider."""
        raise NotImplementedError("Speech transcription is not supported by this provider.")

    async def speak(self, text: str, *, voice: str = "troy") -> bytes:
        """Convert a short text segment to audio when supported by the provider."""
        raise NotImplementedError("Text-to-speech is not supported by this provider.")

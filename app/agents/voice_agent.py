"""Voice-capable assistant agent backed by the provider's chat and audio APIs."""
from __future__ import annotations
from typing import Any
from app.agents.base_agent import BaseAgent


class VoiceAgent(BaseAgent):
    async def run(self, messages: list[dict], **kwargs: Any) -> str:
        return await self.provider.chat(messages, self.model_id, **kwargs)

    async def transcribe(
        self,
        audio: bytes,
        filename: str,
        content_type: str,
        *,
        language: str | None = None,
    ) -> str:
        return await self.provider.transcribe(audio, filename, content_type, language=language)

    async def speak(self, text: str, *, voice: str = "troy") -> bytes:
        return await self.provider.speak(text, voice=voice)

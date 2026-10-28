"""Groq Whisper transcription service."""
from __future__ import annotations

from app.providers.groq_provider import GroqProvider

STATUS = "available"


async def transcribe_audio(
    provider: GroqProvider,
    audio: bytes,
    filename: str,
    content_type: str,
    *,
    language: str | None = None,
) -> str:
    return await provider.transcribe(audio, filename, content_type, language=language)

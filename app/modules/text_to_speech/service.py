"""Groq Orpheus text-to-speech service."""
from __future__ import annotations

from app.providers.groq_provider import GroqProvider

STATUS = "available"


async def synthesize_speech(provider: GroqProvider, text: str, *, voice: str = "troy") -> bytes:
    return await provider.speak(text, voice=voice)

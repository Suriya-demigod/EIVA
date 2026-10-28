"""Groq provider — uses the OpenAI Python SDK pointed at GroqCloud."""
from __future__ import annotations

import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.model_registry import get_model
from app.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class GroqProvider(BaseProvider):
    """Wraps AsyncOpenAI configured for the Groq endpoint."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured. Add it to .env and restart the app.")
        self._client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            timeout=settings.api_timeout,
        )

    # ── non-streaming ───────────────────────────────────────────
    async def chat(
        self,
        messages: list[dict],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            logger.exception("Groq chat request failed")
            raise

    # ── streaming ───────────────────────────────────────────────
    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception:
            logger.exception("Groq streaming request failed")
            raise

    async def transcribe(
        self,
        audio: bytes,
        filename: str,
        content_type: str,
        *,
        language: str | None = None,
    ) -> str:
        model = get_model("speech_to_text")
        params = {
            "file": (filename, audio, content_type),
            "model": model.model_id,
            "temperature": 0.0,
        }
        if language:
            params["language"] = language
        try:
            result = await self._client.audio.transcriptions.create(**params)
            return result.text.strip()
        except Exception:
            logger.exception("Groq transcription request failed")
            raise

    async def speak(self, text: str, *, voice: str = "troy") -> bytes:
        model = get_model("text_to_speech")
        if len(text) > 200:
            raise ValueError("Orpheus accepts at most 200 characters per request.")
        try:
            response = await self._client.audio.speech.create(
                model=model.model_id,
                input=text,
                voice=voice,
                response_format="wav",
            )
            return await response.aread()
        except Exception:
            logger.exception("Groq speech synthesis request failed")
            raise

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.providers.groq_provider import GroqProvider


def make_provider(transcription, speech):
    provider = GroqProvider.__new__(GroqProvider)
    provider._client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(create=transcription),
            speech=SimpleNamespace(create=speech),
        )
    )
    return provider


@pytest.mark.asyncio
async def test_transcribe_uses_registered_whisper_model():
    create = AsyncMock(return_value=SimpleNamespace(text="  hello  "))
    provider = make_provider(create, AsyncMock())

    result = await provider.transcribe(b"audio", "recording.webm", "audio/webm", language="en")

    assert result == "hello"
    create.assert_awaited_once_with(
        file=("recording.webm", b"audio", "audio/webm"),
        model="whisper-large-v3-turbo",
        temperature=0.0,
        language="en",
    )


@pytest.mark.asyncio
async def test_speak_uses_registered_orpheus_model_and_returns_audio():
    response = SimpleNamespace(aread=AsyncMock(return_value=b"wav-bytes"))
    create = AsyncMock(return_value=response)
    provider = make_provider(AsyncMock(), create)

    audio = await provider.speak("Hello", voice="troy")

    assert audio == b"wav-bytes"
    create.assert_awaited_once_with(
        model="canopylabs/orpheus-v1-english",
        input="Hello",
        voice="troy",
        response_format="wav",
    )


@pytest.mark.asyncio
async def test_speak_rejects_input_over_orpheus_limit():
    create = AsyncMock()
    provider = make_provider(AsyncMock(), create)

    with pytest.raises(ValueError, match="200 characters"):
        await provider.speak("x" * 201)

    create.assert_not_awaited()

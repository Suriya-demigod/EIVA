"""Local M10 voice evaluation with mocked Groq audio and chat responses."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request

from backend.api.routes import chat, voice
from backend.core.model_router import ModelRouter
from backend.memory.short_term import ShortTermMemory


class FakeVoiceRouter:
    def __init__(self) -> None:
        self.transcribed: list[tuple[bytes, str, str, str | None]] = []
        self.spoken: list[str] = []
        self.chat_messages: list[list[dict[str, str]]] = []

    def model_for(self, role: str) -> str:
        assert role == "chat"
        return "test-chat-model"

    async def transcribe(self, audio: bytes, filename: str, content_type: str, language=None, request_id=None) -> str:
        self.transcribed.append((audio, filename, content_type, language))
        return "What is the weather?"

    async def synthesize(self, text: str, request_id=None) -> bytes:
        self.spoken.append(text)
        return b"RIFF-test-wav"

    async def complete(self, role: str, messages: list[dict[str, str]], **options):
        self.chat_messages.append(messages)
        return SimpleNamespace(
            model="test-chat-model",
            choices=[SimpleNamespace(message=SimpleNamespace(content="It is sunny today."))],
        )


class FakeTranscriptions:
    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(text="spoken words")


class FakeBinaryResponse:
    async def aread(self) -> bytes:
        return b"RIFF-audio-data"


class FakeSpeech:
    async def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeBinaryResponse()


class FakeAudio:
    def __init__(self) -> None:
        self.transcriptions = FakeTranscriptions()
        self.speech = FakeSpeech()


class FakeGroqClient:
    def __init__(self) -> None:
        self.audio = FakeAudio()


async def evaluate_routes() -> None:
    app = FastAPI()
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")
    app.state.short_term_memory = ShortTermMemory()
    fake_router = FakeVoiceRouter()
    app.dependency_overrides[chat.get_model_router] = lambda: fake_router
    app.dependency_overrides[voice.get_model_router] = lambda: fake_router

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid4()
        return await call_next(request)

    state = {"enabled": False}
    settings = SimpleNamespace(
        voice_enabled=False,
        voice_max_audio_bytes=4,
        local_user_id="voice-evaluator",
        context_max_input_tokens=8192,
        context_max_completion_tokens=256,
    )

    def current_settings():
        settings.voice_enabled = state["enabled"]
        return settings

    with patch("backend.api.routes.voice.get_settings", side_effect=current_settings), \
         patch("backend.api.routes.chat.get_settings", side_effect=current_settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://eiva.test"
        ) as client:
            status = await client.get("/api/v1/voice/status")
            assert status.json() == {"enabled": False}
            disabled = await client.post(
                "/api/v1/voice/transcribe", content=b"wav", headers={"content-type": "audio/wav"}
            )
            assert disabled.status_code == 503

            state["enabled"] = True
            status = await client.get("/api/v1/voice/status")
            assert status.json() == {"enabled": True}
            unsupported = await client.post(
                "/api/v1/voice/transcribe", content=b"wav", headers={"content-type": "text/plain"}
            )
            assert unsupported.status_code == 415
            oversized = await client.post(
                "/api/v1/voice/transcribe", content=b"12345", headers={"content-type": "audio/webm"}
            )
            assert oversized.status_code == 413
            empty = await client.post(
                "/api/v1/voice/transcribe", content=b"", headers={"content-type": "audio/webm"}
            )
            assert empty.status_code == 400

            transcription = await client.post(
                "/api/v1/voice/transcribe?language=en",
                content=b"abc",
                headers={"content-type": "audio/webm;codecs=opus"},
            )
            assert transcription.status_code == 200 and transcription.json() == {"text": "What is the weather?"}
            assert fake_router.transcribed[-1] == (b"abc", "recording.webm", "audio/webm", "en")

            conversation_id = str(uuid4())
            response = await client.post(
                "/api/v1/chat", json={"message": transcription.json()["text"], "conversation_id": conversation_id}
            )
            assert response.status_code == 200 and response.json()["message"]["content"] == "It is sunny today."
            assert fake_router.chat_messages[-1][-1]["content"] == "What is the weather?"

            speech = await client.post("/api/v1/voice/speech", json={"text": "It is sunny today."})
            assert speech.status_code == 200 and speech.content == b"RIFF-test-wav"
            assert speech.headers["content-type"] == "audio/wav"
            assert speech.headers["cache-control"] == "no-store"
            too_long = await client.post("/api/v1/voice/speech", json={"text": "x" * 201})
            assert too_long.status_code == 422


async def evaluate_shared_router() -> None:
    client = FakeGroqClient()
    router = ModelRouter(
        client,
        {"chat": "configured-chat-model"},
        {
            "transcription_model": "whisper-large-v3-turbo",
            "speech_model": "canopylabs/orpheus-v1-english",
            "speech_voice": "hannah",
        },
    )
    transcript = await router.transcribe(b"wav-data", "sample.webm", "audio/webm", "en")
    assert transcript == "spoken words"
    assert client.audio.transcriptions.kwargs["file"] == ("sample.webm", b"wav-data", "audio/webm")
    assert client.audio.transcriptions.kwargs["model"] == "whisper-large-v3-turbo"
    assert client.audio.transcriptions.kwargs["language"] == "en"
    audio_bytes = await router.synthesize("Hello there")
    assert audio_bytes == b"RIFF-audio-data"
    assert client.audio.speech.kwargs == {
        "model": "canopylabs/orpheus-v1-english",
        "voice": "hannah",
        "input": "Hello there",
        "response_format": "wav",
    }


async def main() -> None:
    await evaluate_shared_router()
    await evaluate_routes()
    page = (Path(__file__).resolve().parents[1] / "frontend" / "voice" / "index.html").read_text(encoding="utf-8")
    script = (Path(__file__).resolve().parents[1] / "frontend" / "voice" / "voice.js").read_text(encoding="utf-8")
    assert 'id="listen"' in page and 'id="stop"' in page
    assert "getUserMedia" in script and "requestAnimationFrame" in script and "activeAudio.pause()" in script
    print("voice_runtime_disable_status_and_explicit_mic_controls=passed")
    print("audio_type_empty_and_size_validation=passed")
    print("shared_groq_router_transcription_and_wav_speech=passed")
    print("transcription_chat_history_and_tts_response_flow=passed")
    print("voice_page_vad_and_playback_interrupt_hooks=passed")


if __name__ == "__main__":
    asyncio.run(main())

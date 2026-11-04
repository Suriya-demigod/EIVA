"""Explicitly enabled voice endpoints backed by the shared Groq model router."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from backend.config import get_settings
from backend.core.model_router import ModelRouter, get_model_router

router = APIRouter(prefix="/voice", tags=["voice"])
SUPPORTED_AUDIO_TYPES = {
    "audio/flac": ("recording.flac", "audio/flac"),
    "audio/m4a": ("recording.m4a", "audio/mp4"),
    "audio/mp4": ("recording.mp4", "audio/mp4"),
    "audio/mpeg": ("recording.mp3", "audio/mpeg"),
    "audio/mp3": ("recording.mp3", "audio/mpeg"),
    "audio/ogg": ("recording.ogg", "audio/ogg"),
    "audio/wav": ("recording.wav", "audio/wav"),
    "audio/x-wav": ("recording.wav", "audio/wav"),
    "audio/webm": ("recording.webm", "audio/webm"),
}


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=200)


def _require_enabled() -> None:
    if not get_settings().voice_enabled:
        raise HTTPException(status_code=503, detail="Voice features are disabled")


@router.get("/status", summary="Get voice feature availability")
async def voice_status() -> dict[str, bool]:
    return {"enabled": get_settings().voice_enabled}


@router.post("/transcribe", summary="Transcribe one microphone recording")
async def transcribe(
    request: Request,
    language: str | None = Query(default=None, min_length=2, max_length=2, pattern="^[a-z]{2}$"),
    model_router: ModelRouter = Depends(get_model_router),
) -> dict[str, str]:
    _require_enabled()
    settings = get_settings()
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    file_info = SUPPORTED_AUDIO_TYPES.get(content_type)
    if not file_info:
        raise HTTPException(status_code=415, detail="Unsupported audio type")

    announced_length = request.headers.get("content-length")
    if announced_length and announced_length.isdigit() and int(announced_length) > settings.voice_max_audio_bytes:
        raise HTTPException(status_code=413, detail="Audio recording exceeds the configured size limit")
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > settings.voice_max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio recording exceeds the configured size limit")
        chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio recording is empty")

    filename, normalized_type = file_info
    transcript = await model_router.transcribe(
        audio_bytes, filename, normalized_type, language, request.state.request_id
    )
    if not transcript:
        raise HTTPException(status_code=422, detail="No speech was detected in the recording")
    return {"text": transcript}


@router.post("/speech", summary="Convert a short response to spoken audio")
async def speech(
    payload: SpeechRequest,
    request: Request,
    model_router: ModelRouter = Depends(get_model_router),
) -> Response:
    _require_enabled()
    audio_bytes = await model_router.synthesize(payload.text, request.state.request_id)
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-Request-ID": str(request.state.request_id)},
    )

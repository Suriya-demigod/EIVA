"""Voice endpoints for browser-recorded audio and spoken replies."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.errors import provider_http_error
from app.core.agent_registry import get_groq_provider
from app.core.model_registry import get_model
from app.models.request_models import SpeakRequest
from app.models.response_models import TranscriptionResponse
from app.modules.speech_to_text.service import transcribe_audio
from app.modules.text_to_speech.service import synthesize_speech

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["voice"])

MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_TYPES = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


@router.post("/voice/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
) -> TranscriptionResponse:
    """Transcribe one browser-recorded or uploaded audio file with Whisper."""
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(415, "Unsupported audio type. Use WebM, WAV, MP3, M4A, MP4, OGG, or FLAC.")
    if language and not re.fullmatch(r"[a-zA-Z]{2}", language):
        raise HTTPException(422, "Language must be a two-letter ISO 639-1 code, such as en or hi.")

    audio = await file.read(MAX_AUDIO_BYTES + 1)
    await file.close()
    if not audio:
        raise HTTPException(400, "The uploaded audio file is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio uploads are limited to 25 MB.")

    model = get_model("speech_to_text")
    content_type = file.content_type or SUPPORTED_AUDIO_TYPES[extension]
    try:
        text = await transcribe_audio(
            get_groq_provider(),
            audio,
            file.filename or f"recording{extension}",
            content_type,
            language=language.lower() if language else None,
        )
        return TranscriptionResponse(text=text, model=model.model_id)
    except Exception as exc:
        logger.exception("Speech transcription failed")
        raise provider_http_error(exc) from exc


@router.post("/voice/speak")
async def speak(request: SpeakRequest) -> Response:
    """Synthesize one short English speech segment as WAV audio."""
    text = request.text.strip()
    if not text:
        raise HTTPException(422, "Text must contain non-whitespace characters.")
    if len(text) > 200:
        raise HTTPException(422, "Speech segments must be 200 characters or fewer.")
    try:
        audio = await synthesize_speech(get_groq_provider(), text, voice=request.voice)
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:
        logger.exception("Speech synthesis failed")
        raise provider_http_error(exc) from exc

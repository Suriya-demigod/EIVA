"""Groq-only model gateway with role selection and safe call telemetry."""

from functools import lru_cache
import json
import logging
from pathlib import Path
import time
from typing import Any
from uuid import UUID
import base64

import yaml
from groq import AsyncGroq, GroqError

from backend.config import get_settings

logger = logging.getLogger("eiva.models")


def completion_text(response: Any, *, fallback: str = "") -> str:
    """Return the first completion's text or fail clearly on malformed responses."""
    choices = getattr(response, "choices", None)
    if not choices:
        raise ValueError("Model provider returned no choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else fallback


class ModelRouter:
    def __init__(
        self,
        client: AsyncGroq,
        models: dict[str, str],
        audio: dict[str, str] | None = None,
        pricing: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._client = client
        self._models = models
        self._audio = audio or {}
        self._pricing = pricing or {}

    def estimate_cost(self, model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
        rates = self._pricing.get(model)
        if rates is None or prompt_tokens is None or completion_tokens is None:
            return None
        input_rate = rates.get("input_usd_per_million_tokens")
        output_rate = rates.get("output_usd_per_million_tokens")
        if input_rate is None or output_rate is None:
            return None
        return round((prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000, 8)

    def model_for(self, role: str) -> str:
        try:
            return self._models[role]
        except KeyError as exc:
            raise ValueError(f"No Groq model configured for role: {role}") from exc

    async def complete(
        self,
        role: str,
        messages: list[dict[str, Any]],
        **options: Any,
    ) -> Any:
        model = self.model_for(role)
        request_id = options.pop("request_id", None)
        started = time.perf_counter()
        is_stream = bool(options.get("stream", False))
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                **options,
            )
        except GroqError as exc:
            logger.warning(
                "EIVA_MODEL_CALL %s",
                json.dumps(
                    {
                        "event": "failed",
                        "provider": "groq",
                        "role": role,
                        "model": model,
                        "request_id": str(request_id) if request_id else None,
                        "latency_ms": round((time.perf_counter() - started) * 1000),
                        "error_type": type(exc).__name__,
                    },
                    sort_keys=True,
                ),
            )
            raise

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        event = {
            "event": "stream_started" if is_stream else "completed",
            "provider": "groq",
            "role": role,
            "model": model,
            "request_id": str(request_id) if request_id else None,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        estimated_cost = self.estimate_cost(model, prompt_tokens, completion_tokens)
        if estimated_cost is not None:
            event["estimated_cost_usd"] = estimated_cost
        logger.info(
            "EIVA_MODEL_CALL %s",
            json.dumps(event, sort_keys=True),
        )
        return response

    async def analyze_image(
        self,
        question: str,
        image_bytes: bytes,
        mime_type: str,
        request_id: UUID | None = None,
    ) -> tuple[str, str]:
        """Answer a question about one user-supplied image using the configured vision role."""
        model = self.model_for("vision")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        completion = await self.complete(
            "vision",
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                        },
                    ],
                }
            ],
            request_id=request_id,
            max_completion_tokens=1024,
            temperature=0.2,
        )
        answer = completion_text(completion)
        return answer, completion.model or model

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        language: str | None = None,
        request_id: UUID | None = None,
    ) -> str:
        """Transcribe user supplied audio through the existing Groq client."""
        model = self._audio.get("transcription_model")
        if not model:
            raise ValueError("No voice transcription model configured")
        started = time.perf_counter()
        options: dict[str, Any] = {
            "file": (filename, audio_bytes, content_type),
            "model": model,
            "response_format": "json",
            "temperature": 0.0,
        }
        if language:
            options["language"] = language
        try:
            response = await self._client.audio.transcriptions.create(**options)
        except GroqError as exc:
            logger.warning(
                "EIVA_AUDIO_CALL %s",
                json.dumps(
                    {"event": "failed", "operation": "transcription", "model": model,
                     "request_id": str(request_id) if request_id else None,
                     "latency_ms": round((time.perf_counter() - started) * 1000),
                     "error_type": type(exc).__name__},
                    sort_keys=True,
                ),
            )
            raise
        logger.info(
            "EIVA_AUDIO_CALL %s",
            json.dumps(
                {"event": "completed", "operation": "transcription", "model": model,
                 "request_id": str(request_id) if request_id else None,
                 "latency_ms": round((time.perf_counter() - started) * 1000),
                 "audio_bytes": len(audio_bytes)},
                sort_keys=True,
            ),
        )
        return response.text.strip()

    async def synthesize(self, text: str, request_id: UUID | None = None) -> bytes:
        """Generate WAV speech through the existing Groq client."""
        model = self._audio.get("speech_model")
        voice = self._audio.get("speech_voice")
        if not model or not voice:
            raise ValueError("No voice speech model and voice are configured")
        started = time.perf_counter()
        try:
            response = await self._client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                response_format="wav",
            )
            audio_bytes = await response.aread()
        except GroqError as exc:
            logger.warning(
                "EIVA_AUDIO_CALL %s",
                json.dumps(
                    {"event": "failed", "operation": "speech", "model": model,
                     "request_id": str(request_id) if request_id else None,
                     "latency_ms": round((time.perf_counter() - started) * 1000),
                     "error_type": type(exc).__name__},
                    sort_keys=True,
                ),
            )
            raise
        logger.info(
            "EIVA_AUDIO_CALL %s",
            json.dumps(
                {"event": "completed", "operation": "speech", "model": model,
                 "request_id": str(request_id) if request_id else None,
                 "latency_ms": round((time.perf_counter() - started) * 1000),
                 "output_bytes": len(audio_bytes)},
                sort_keys=True,
            ),
        )
        return audio_bytes

    async def aclose(self) -> None:
        await self._client.close()


@lru_cache
def get_model_router() -> ModelRouter:
    settings = get_settings()
    config_path = Path(settings.models_config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if config.get("provider") != "groq":
        raise ValueError("EIVA supports Groq as its only model provider")
    models = config.get("roles", {})
    if not models:
        raise ValueError(f"No model roles configured in {config_path}")
    client = AsyncGroq(
        api_key=settings.groq_api_key,
        timeout=settings.groq_timeout_seconds,
        max_retries=settings.groq_max_retries,
    )
    return ModelRouter(client, models, config.get("audio", {}), config.get("pricing_usd_per_million_tokens", {}))


async def close_model_router() -> None:
    if get_model_router.cache_info().currsize:
        router = get_model_router()
        get_model_router.cache_clear()
        await router.aclose()

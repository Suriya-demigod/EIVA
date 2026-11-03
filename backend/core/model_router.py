"""Groq-only model gateway with role selection and safe call telemetry."""

from functools import lru_cache
import json
import logging
from pathlib import Path
import time
from typing import Any

import yaml
from groq import AsyncGroq, GroqError

from backend.config import get_settings

logger = logging.getLogger("eiva.models")


class ModelRouter:
    def __init__(self, client: AsyncGroq, models: dict[str, str]) -> None:
        self._client = client
        self._models = models

    def model_for(self, role: str) -> str:
        try:
            return self._models[role]
        except KeyError as exc:
            raise ValueError(f"No Groq model configured for role: {role}") from exc

    async def complete(
        self,
        role: str,
        messages: list[dict[str, str]],
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
        logger.info(
            "EIVA_MODEL_CALL %s",
            json.dumps(
                {
                    "event": "stream_started" if is_stream else "completed",
                    "provider": "groq",
                    "role": role,
                    "model": model,
                    "request_id": str(request_id) if request_id else None,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                },
                sort_keys=True,
            ),
        )
        return response

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
    return ModelRouter(client, models)


async def close_model_router() -> None:
    if get_model_router.cache_info().currsize:
        router = get_model_router()
        get_model_router.cache_clear()
        await router.aclose()

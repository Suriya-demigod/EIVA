"""Central model registry — single source of truth for all model IDs and capabilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ModelCapability(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    VISION = "vision"
    SAFETY = "safety"
    MULTILINGUAL = "multilingual"
    FUNCTION_CALLING = "function_calling"
    IMAGE_GENERATION = "image_generation"


@dataclass
class ModelInfo:
    """Metadata for a registered model."""

    model_id: str
    capability: ModelCapability
    display_name: str
    provider: str = "groq"
    context_window: int = 131_072
    max_output_tokens: int = 65_536
    is_available: bool = True
    description: str = ""
    extra: dict = field(default_factory=dict)


# ── Model registry. Availability means implemented in this app, not that
# the configured Groq account has been checked for access. ──────────
_MODELS: dict[str, ModelInfo] = {
    "fast_chat": ModelInfo(
        model_id="openai/gpt-oss-20b",
        capability=ModelCapability.CHAT,
        display_name="GPT-OSS 20B (Fast)",
        description="Fast MoE model — 21B params, 3.6B active. Default for chat.",
    ),
    "reasoning": ModelInfo(
        model_id="openai/gpt-oss-120b",
        capability=ModelCapability.REASONING,
        display_name="GPT-OSS 120B (Reasoning)",
        description="Flagship reasoning model — 117B params, 5.1B active.",
    ),
    "speech_to_text": ModelInfo(
        model_id="whisper-large-v3-turbo",
        capability=ModelCapability.SPEECH_TO_TEXT,
        display_name="Whisper Large v3 Turbo",
        context_window=0,
        max_output_tokens=0,
        is_available=True,
        description="Multilingual speech transcription for recorded audio.",
    ),
    "text_to_speech": ModelInfo(
        model_id="canopylabs/orpheus-v1-english",
        capability=ModelCapability.TEXT_TO_SPEECH,
        display_name="Orpheus English",
        context_window=0,
        max_output_tokens=0,
        is_available=True,
        description="Expressive English speech synthesis (200 characters per request).",
    ),
    "vision": ModelInfo(
        model_id="qwen/qwen3.8-27b",
        capability=ModelCapability.VISION,
        display_name="Qwen 3.8 27B",
        is_available=False,  # Phase 5
        description="Vision-language model for image understanding.",
    ),
    "safety": ModelInfo(
        model_id="openai/gpt-oss-safeguard-20b",
        capability=ModelCapability.SAFETY,
        display_name="GPT-OSS Safeguard 20B",
        is_available=False,  # Phase 6
        description="Content safety classification.",
    ),
    "multilingual": ModelInfo(
        model_id="openai/gpt-oss-20b",
        capability=ModelCapability.MULTILINGUAL,
        display_name="GPT-OSS 20B (Multilingual)",
        is_available=False,  # Phase 6
        description="Multilingual routing.",
    ),
    "function_calling": ModelInfo(
        model_id="openai/gpt-oss-20b",
        capability=ModelCapability.FUNCTION_CALLING,
        display_name="GPT-OSS 20B (Tools)",
        is_available=False,  # Phase 6
        description="Function-calling capable model.",
    ),
    "image_generation": ModelInfo(
        model_id="placeholder",
        capability=ModelCapability.IMAGE_GENERATION,
        display_name="Image Generation (Future)",
        provider="external",
        is_available=False,  # Phase 8
        description="Future external image generation provider.",
    ),
}


def get_model(key: str) -> Optional[ModelInfo]:
    return _MODELS.get(key)


def get_default_model() -> ModelInfo:
    return _MODELS["fast_chat"]


def list_models() -> dict[str, ModelInfo]:
    return dict(_MODELS)

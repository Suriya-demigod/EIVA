"""Agent registry — creates and caches agent instances."""
from __future__ import annotations

from functools import lru_cache

from app.providers.groq_provider import GroqProvider
from app.core.model_registry import get_model
from app.agents.chat_agent import ChatAgent
from app.agents.reasoning_agent import ReasoningAgent
from app.agents.voice_agent import VoiceAgent


@lru_cache
def _provider() -> GroqProvider:
    return GroqProvider()


def get_groq_provider() -> GroqProvider:
    """Return the shared configured Groq provider."""
    return _provider()


@lru_cache
def get_chat_agent() -> ChatAgent:
    m = get_model("fast_chat")
    return ChatAgent(_provider(), m.model_id)


@lru_cache
def get_reasoning_agent() -> ReasoningAgent:
    m = get_model("reasoning")
    return ReasoningAgent(_provider(), m.model_id)


@lru_cache
def get_voice_agent() -> VoiceAgent:
    m = get_model("fast_chat")
    return VoiceAgent(_provider(), m.model_id)

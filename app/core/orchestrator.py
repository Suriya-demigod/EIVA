"""Orchestrator — routes requests to the right agent and model."""
from __future__ import annotations

import logging
import re
from typing import AsyncIterator

from app.core.agent_registry import get_chat_agent, get_reasoning_agent

logger = logging.getLogger(__name__)

# Simple heuristics for reasoning escalation
_REASONING_KEYWORDS = {
    "explain step by step", "reason through", "think carefully",
    "analyze in detail", "compare and contrast", "prove that",
    "solve this problem", "break down", "deep analysis",
}


def _needs_reasoning(message: str) -> bool:
    """Lightweight check — no extra model call."""
    lower = message.lower()
    return any(kw in lower for kw in _REASONING_KEYWORDS)


def select_agent(message: str):
    """Select the lowest-cost suitable agent without an extra model call."""
    if _needs_reasoning(message):
        logger.info("Escalating request to reasoning agent")
        return get_reasoning_agent()
    return get_chat_agent()


def _asks_model_identity(message: str) -> bool:
    text = re.sub(r"[^a-z0-9]+", " ", message.lower()).strip()
    if text in {"who are you", "what are you", "are you chatgpt", "are you gpt 4"}:
        return True
    return bool(re.search(
        r"\b(what|which) model\b.*\b(am i talking to|are you|do you use|is this|runs this chat)\b",
        text,
    ))


def _identity_reply(agent) -> str:
    return (
        f"I'm Ruby, powered by `{agent.model_id}` through GroqCloud. "
        "I'm not the ChatGPT service."
    )


async def handle_chat(messages: list[dict]) -> str:
    """Pick agent, run, return full text."""
    last = messages[-1]["content"] if messages else ""
    agent = select_agent(last)
    if _asks_model_identity(last):
        return _identity_reply(agent)
    return await agent.run(messages)


async def handle_chat_stream(messages: list[dict]) -> AsyncIterator[str]:
    """Pick agent, stream text chunks."""
    last = messages[-1]["content"] if messages else ""
    agent = select_agent(last)
    if _asks_model_identity(last):
        yield _identity_reply(agent)
        return
    async for chunk in agent.run_stream(messages):
        yield chunk


def selected_model_id(message: str) -> str:
    """Return the model ID selected for a single user turn."""
    return select_agent(message).model_id

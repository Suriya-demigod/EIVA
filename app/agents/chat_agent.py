"""Chat agent — handles normal conversational turns."""
from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent

SYSTEM_PROMPT = (
    "You are Ruby, a friendly and helpful AI assistant. "
    "Your configured model ID is {model_id}, served through GroqCloud. "
    "Never claim to be ChatGPT, GPT-4, or a different model or provider. "
    "If asked which model runs this chat, state the configured model ID and GroqCloud. "
    "Provide clear, concise, accurate answers, and say when you are uncertain."
)


class ChatAgent(BaseAgent):
    def prepare_messages(self, messages: list[dict]) -> list[dict]:
        return [{"role": "system", "content": SYSTEM_PROMPT.format(model_id=self.model_id)}, *messages]

    async def run(self, messages: list[dict], **kwargs: Any) -> str:
        return await self.provider.chat(self.prepare_messages(messages), self.model_id, **kwargs)

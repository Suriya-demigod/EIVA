"""Stub agents for later phases — all return 'unavailable' until implemented."""
from __future__ import annotations
from typing import Any
from app.agents.base_agent import BaseAgent


class ReasoningAgent(BaseAgent):
    def prepare_messages(self, messages: list[dict]) -> list[dict]:
        return [{
            "role": "system",
            "content": f"You are Ruby, a careful problem-solving assistant. Your configured model ID is {self.model_id}, served through GroqCloud. Never claim to be ChatGPT, GPT-4, or another model or provider. If asked which model runs this chat, state the configured model ID and GroqCloud. Analyze complex problems thoroughly, then give a clear answer with a concise explanation. Do not reveal private chain-of-thought.",
        }, *messages]

    async def run(self, messages: list[dict], **kwargs: Any) -> str:
        return await self.provider.chat(self.prepare_messages(messages), self.model_id, **kwargs)

"""Stub agents for future phases."""
from __future__ import annotations
from typing import Any
from app.agents.base_agent import BaseAgent


class SafetyAgent(BaseAgent):
    async def run(self, messages: list[dict], **kwargs: Any) -> str:
        return "⚠️ Safety classification is not yet available (Phase 6)."

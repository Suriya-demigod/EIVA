"""Pydantic request models."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=100_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = False

    @model_validator(mode="after")
    def last_message_must_be_user(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("The final message must have role 'user'.")
        return self


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    voice: Literal["autumn", "diana", "hannah", "austin", "daniel", "troy"] = "troy"

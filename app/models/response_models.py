"""Pydantic response models."""
from __future__ import annotations

from pydantic import BaseModel


class ChatResponse(BaseModel):
    reply: str
    model: str
    usage: dict | None = None


class TranscriptionResponse(BaseModel):
    text: str
    model: str


class HealthResponse(BaseModel):
    status: str
    version: str
    provider_configured: bool
    models: dict[str, bool]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None

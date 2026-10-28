"""Core configuration loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env from project root
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)


class Settings(BaseSettings):
    """Application settings — all secrets come from .env."""

    app_name: str = "Ruby AI"
    app_version: str = "0.1.0"
    debug: bool = False

    # Groq
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Conversation
    max_history_messages: int = 20
    max_sessions: int = 500

    # Timeouts (seconds)
    api_timeout: float = 30.0
    cors_origins: list[str] = [
        "http://127.0.0.1:8000", "http://localhost:8000",
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:3000", "http://localhost:3000",
    ]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Application configuration for EIVA."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EIVA"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    groq_api_key: str
    groq_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    groq_max_retries: int = Field(default=2, ge=0, le=5)
    local_user_id: str = Field(default="local", min_length=1, max_length=128)
    context_max_input_tokens: int = Field(default=8192, ge=512, le=32768)
    context_max_completion_tokens: int = Field(default=2048, ge=128, le=8192)
    context_max_history_messages: int = Field(default=80, ge=2, le=500)
    context_max_conversations: int = Field(default=512, ge=1, le=10000)
    models_config_path: str = "config/models.yaml"
    agents_config_path: str = "config/agents.yaml"
    skills_config_dir: str = "config/skills"
    tool_bindings_config_path: str = "config/tool_bindings.yaml"
    mcp_servers_config_path: str = "config/mcp_servers.yaml"
    permissions_config_path: str = "config/permissions.yaml"
    database_path: str = "data/eiva.sqlite3"
    rag_allowed_roots: str = "data/knowledge"
    rag_max_file_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    rag_chunk_chars: int = Field(default=1_100, ge=400, le=4_000)
    rag_chunk_overlap_chars: int = Field(default=175, ge=0, le=500)
    rag_embedding_model: str = "BAAI/bge-small-en-v1.5"
    rag_embedding_dimension: int = Field(default=384, ge=1, le=4_096)
    rag_embedding_cache_dir: str = "data/models"
    rag_retrieval_top_k: int = Field(default=6, ge=5, le=8)
    rag_candidate_k: int = Field(default=30, ge=8, le=100)

    @model_validator(mode="after")
    def validate_rag_chunk_overlap(self) -> "Settings":
        if self.rag_chunk_overlap_chars >= self.rag_chunk_chars:
            raise ValueError("RAG_CHUNK_OVERLAP_CHARS must be smaller than RAG_CHUNK_CHARS")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

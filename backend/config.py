"""Application configuration for EIVA."""

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
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
    voice_enabled: bool = False
    voice_max_audio_bytes: int = Field(default=25_000_000, ge=1_024, le=100_000_000)
    vision_max_image_bytes: int = Field(default=20_000_000, ge=1_024, le=20_000_000)
    a2a_enabled: bool = False
    a2a_server_token: SecretStr | None = None
    a2a_agent_name: str = Field(default="EIVA", min_length=2, max_length=80)
    a2a_agent_description: str = Field(default="EIVA local personal assistant", min_length=1, max_length=500)
    a2a_public_url: str = "http://127.0.0.1:8000/a2a/v1"
    a2a_peers_config_path: str = "config/a2a_peers.yaml"

    @model_validator(mode="after")
    def validate_rag_chunk_overlap(self) -> "Settings":
        if self.rag_chunk_overlap_chars >= self.rag_chunk_chars:
            raise ValueError("RAG_CHUNK_OVERLAP_CHARS must be smaller than RAG_CHUNK_CHARS")
        if self.a2a_enabled:
            token = self.a2a_server_token.get_secret_value() if self.a2a_server_token else ""
            if len(token) < 32:
                raise ValueError("A2A_SERVER_TOKEN must be at least 32 characters when A2A is enabled")
            parsed_public_url = urlsplit(self.a2a_public_url)
            secure_public_url = parsed_public_url.scheme == "https" or (
                parsed_public_url.scheme == "http" and parsed_public_url.hostname in {"127.0.0.1", "localhost", "::1"}
            )
            if not secure_public_url or not parsed_public_url.hostname or parsed_public_url.username or parsed_public_url.password or parsed_public_url.query or parsed_public_url.fragment:
                raise ValueError("A2A_PUBLIC_URL must use HTTPS (HTTP is allowed only for loopback)")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

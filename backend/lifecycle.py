"""Application startup and shutdown lifecycle hooks."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from backend.core.model_router import close_model_router
from backend.config import get_settings
from backend.database import Database
from backend.database.repositories import ConversationRepository, MemoryRepository, TaskRepository
from backend.memory.manager import MemoryManager
from backend.memory.short_term import ShortTermMemory
from backend.rag.embeddings import LocalEmbedder
from backend.rag.repository import RagRepository
from backend.rag.service import RagService
from backend.agents.registry import get_agent_registry
from backend.agents.a2a import A2AClient
from backend.agents.messaging import AgentMessageBus
from backend.orchestration.events import TaskEventBus
from backend.orchestration.supervisor import WorkflowSupervisor
from backend.tasks.manager import TaskManager
from backend.tools.gateway import ToolGateway
from backend.tools.approvals import ApprovalManager


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize lazy tool access and close pooled clients on shutdown."""
    settings = get_settings()
    database = Database(Path(settings.database_path))
    applied_migrations = database.initialize()
    if applied_migrations:
        logging.getLogger("eiva.database").info("Applied database migrations: %s", applied_migrations)
    app.state.database = database
    task_repository = TaskRepository(database)
    app.state.task_repository = task_repository
    app.state.event_bus = TaskEventBus(persist_event=task_repository.save_event)
    app.state.agent_message_bus = AgentMessageBus()
    app.state.a2a_client = A2AClient.from_yaml(
        Path(settings.a2a_peers_config_path), timeout_seconds=settings.groq_timeout_seconds
    )
    app.state.approval_manager = ApprovalManager()
    app.state.tool_gateway = ToolGateway.from_files(
        bindings_path=Path(settings.tool_bindings_config_path),
        servers_path=Path(settings.mcp_servers_config_path),
        permissions_path=Path(settings.permissions_config_path),
        approval_manager=app.state.approval_manager,
        task_event_sink=app.state.event_bus.publish,
    )
    app.state.task_manager = TaskManager(app.state.event_bus, repository=task_repository)
    app.state.short_term_memory = ShortTermMemory(
        max_conversations=settings.context_max_conversations,
        max_history_messages=settings.context_max_history_messages,
        repository=ConversationRepository(database),
    )
    app.state.memory_manager = MemoryManager(MemoryRepository(database))
    allowed_roots = [Path(item.strip()) for item in settings.rag_allowed_roots.split(os.pathsep) if item.strip()]
    for root in allowed_roots:
        root.mkdir(parents=True, exist_ok=True)
    rag_repository = RagRepository(database, settings.rag_embedding_dimension)
    rag_embedder = LocalEmbedder(
        settings.rag_embedding_model,
        settings.rag_embedding_dimension,
        Path(settings.rag_embedding_cache_dir),
    )
    app.state.rag_service = RagService(
        rag_repository,
        rag_embedder,
        allowed_roots,
        max_file_bytes=settings.rag_max_file_bytes,
        chunk_chars=settings.rag_chunk_chars,
        overlap_chars=settings.rag_chunk_overlap_chars,
        candidate_k=settings.rag_candidate_k,
        top_k=settings.rag_retrieval_top_k,
    )
    agent_registry = get_agent_registry()
    agent_registry.message_bus = app.state.agent_message_bus
    app.state.supervisor = WorkflowSupervisor(
        app.state.task_manager,
        app.state.event_bus,
        agent_registry,
        app.state.tool_gateway,
        max_concurrent=4,
    )
    try:
        yield
    finally:
        await app.state.task_manager.shutdown()
        app.state.approval_manager.cancel_all()
        await app.state.tool_gateway.close()
        await app.state.a2a_client.close()
        await close_model_router()

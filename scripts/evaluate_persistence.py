"""M08 persistence, scoping, restart-recovery, and memory-control evaluation."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI

from backend.api.routes.memories import router as memory_router
from backend.config import get_settings
from backend.database import Database
from backend.database.models import TaskCheckpointRecord
from backend.database.repositories import ConversationRepository, MemoryRepository, TaskRepository
from backend.memory.manager import MemoryManager
from backend.memory.short_term import ContextScope, ShortTermMemory
from backend.lifecycle import app_lifespan
from backend.main import app as eiva_app
from backend.orchestration.events import TaskEventBus
from backend.tasks.manager import TaskManager, TaskRecord, TaskStatus


def verify_storage(path: Path) -> tuple[Database, MemoryManager, TaskRepository]:
    database = Database(path)
    assert database.initialize() == [1, 2, 3]
    assert database.initialize() == []
    assert database.applied_migrations() == [
        (1, "001_initial.sql"), (2, "002_knowledge_index.sql"), (3, "003_hybrid_rag.sql")
    ]

    conversation_repo = ConversationRepository(database)
    memory = ShortTermMemory(max_conversations=8, max_history_messages=4, repository=conversation_repo)
    conversation_id = uuid4()
    task_a = ContextScope("user-a", conversation_id, uuid4())
    task_b = ContextScope("user-a", conversation_id, uuid4())
    other_user = ContextScope("user-b", conversation_id, task_a.task_id)
    memory.append_exchange(task_a, "first question", "first answer")
    memory.append_exchange(task_a, "second question", "second answer")
    memory.append_exchange(task_a, "third question", "third answer")
    assert [item["content"] for item in memory.get_history(task_a)] == [
        "second question", "second answer", "third question", "third answer"
    ]
    assert memory.history_was_truncated(task_a)
    assert memory.get_history(task_b) == [] and memory.get_history(other_user) == []

    memory_manager = MemoryManager(MemoryRepository(database))
    saved = memory_manager.create(
        user_id="user-a", content="Prefers short, evidence-based answers", tags=["style", "work"], importance=4
    )
    memory_manager.create(user_id="user-b", content="Private other-user note", tags=["private"], importance=5)
    assert memory_manager.search("evidence based answers", "user-a")[0].id == saved.id
    assert memory_manager.search("Private other-user note", "user-a") == []
    assert memory_manager.get(saved.id, "user-b") is None
    assert not memory_manager.delete(saved.id, "user-b")
    assert memory_manager.get(saved.id, "user-a") is not None
    reloaded_conversations = ConversationRepository(Database(path))
    assert reloaded_conversations.get_history(task_a) == memory.get_history(task_a)
    reloaded_memories = MemoryManager(MemoryRepository(Database(path)))
    assert reloaded_memories.get(saved.id, "user-a").content == saved.content

    task_repo = TaskRepository(database)
    completed = TaskRecord(
        request_id=uuid4(), workflow="research", status=TaskStatus.completed,
        description="persisted task", progress_percent=100, result={"message": "stored"},
    )
    interrupted = TaskRecord(request_id=uuid4(), workflow="coding", description="interrupted task")
    task_repo.save_task(completed.model_dump(mode="json"))
    task_repo.save_task(interrupted.model_dump(mode="json"))
    bus = TaskEventBus(persist_event=task_repo.save_event)
    bus.publish(completed.id, "task.queued", {"status": "queued"})
    task_repo.save_checkpoint(
        TaskCheckpointRecord(task_id=completed.id, name="after-researcher", payload={"marker": "checkpoint"})
    )

    restarted_bus = TaskEventBus(persist_event=task_repo.save_event)
    restarted = TaskManager(restarted_bus, repository=TaskRepository(Database(path)))
    assert restarted.get(completed.id).result == {"message": "stored"}
    assert restarted.get(interrupted.id).status == TaskStatus.failed
    assert restarted.get(interrupted.id).error == "Task interrupted by application restart"
    assert [event.sequence for event in restarted_bus.history(completed.id)] == [1]
    assert [event.sequence for event in restarted_bus.history(interrupted.id)] == [1]
    assert restarted.checkpoints(completed.id)[0].payload == {"marker": "checkpoint"}
    assert memory_manager.delete(saved.id, "user-a")
    assert memory_manager.get(saved.id, "user-a") is None
    return database, memory_manager, task_repo


async def verify_memory_api(manager: MemoryManager) -> None:
    app = FastAPI()
    app.include_router(memory_router, prefix="/api/v1")
    app.state.memory_manager = manager
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://eiva.test") as client:
        response = await client.post(
            "/api/v1/memories",
            json={"content": "API memory marker", "tags": ["evaluation"], "importance": 3},
        )
        assert response.status_code == 201, response.text
        memory_id = response.json()["id"]
        listing = await client.get("/api/v1/memories", params={"query": "API memory marker"})
        assert listing.status_code == 200 and listing.json()["items"][0]["id"] == memory_id
        detail = await client.get(f"/api/v1/memories/{memory_id}")
        assert detail.status_code == 200
        deleted = await client.delete(f"/api/v1/memories/{memory_id}")
        assert deleted.status_code == 204
        missing = await client.get(f"/api/v1/memories/{memory_id}")
        assert missing.status_code == 404


async def verify_application_lifecycle(database_path: Path) -> None:
    settings = get_settings().model_copy(update={"database_path": str(database_path)})
    with patch("backend.lifecycle.get_settings", return_value=settings):
        async with app_lifespan(eiva_app):
            assert eiva_app.state.database.path == database_path
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=eiva_app), base_url="http://eiva.test"
            ) as client:
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/api/v1/tasks")).status_code == 200
                assert (await client.get("/api/v1/memories")).status_code == 200


async def main() -> None:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "eiva.sqlite3"
        _, manager, _ = verify_storage(path)
        await verify_memory_api(manager)
        await verify_application_lifecycle(Path(temporary) / "application.sqlite3")
    print("migrations_repeatable=passed conversation_restart_scope=passed truncation=passed")
    print("task_restart_recovery=passed event_persistence=passed checkpoint_persistence=passed")
    print("memory_retrieval_scope=passed inspect_delete_api=passed")


if __name__ == "__main__":
    asyncio.run(main())

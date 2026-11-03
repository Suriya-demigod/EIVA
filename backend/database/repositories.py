"""SQLite repositories for conversation, task, checkpoint, and memory records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from backend.database import Database
from backend.database.models import MemoryRecord, TaskCheckpointRecord
if TYPE_CHECKING:
    from backend.memory.short_term import ContextScope


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class ConversationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _key(scope: ContextScope) -> tuple[str, str, str]:
        return scope.user_id, str(scope.conversation_id), str(scope.task_id or "")

    def get_history(self, scope: ContextScope) -> list[dict[str, str]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT role, content FROM messages WHERE user_id=? AND conversation_id=? AND task_scope=? ORDER BY id",
                self._key(scope),
            ).fetchall()
        return [{"role": row[0], "content": row[1]} for row in rows]

    def was_truncated(self, scope: ContextScope) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT history_truncated FROM conversations WHERE user_id=? AND conversation_id=? AND task_scope=?",
                self._key(scope),
            ).fetchone()
        return bool(row[0]) if row else False

    def append_exchange(self, scope: ContextScope, user_message: str, assistant_message: str, max_messages: int) -> None:
        user_id, conversation_id, task_scope = self._key(scope)
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO conversations(user_id, conversation_id, task_scope, created_at, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, conversation_id, task_scope) DO UPDATE SET updated_at=excluded.updated_at",
                (user_id, conversation_id, task_scope, now, now),
            )
            connection.executemany(
                "INSERT INTO messages(user_id, conversation_id, task_scope, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (user_id, conversation_id, task_scope, "user", user_message, now),
                    (user_id, conversation_id, task_scope, "assistant", assistant_message, now),
                ],
            )
            count = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE user_id=? AND conversation_id=? AND task_scope=?",
                (user_id, conversation_id, task_scope),
            ).fetchone()[0]
            excess = count - max_messages
            if excess > 0:
                remove_count = ((excess + 1) // 2) * 2
                old_ids = connection.execute(
                    "SELECT id FROM messages WHERE user_id=? AND conversation_id=? AND task_scope=? ORDER BY id LIMIT ?",
                    (user_id, conversation_id, task_scope, remove_count),
                ).fetchall()
                connection.executemany("DELETE FROM messages WHERE id=?", [(row[0],) for row in old_ids])
                connection.execute(
                    "UPDATE conversations SET history_truncated=1 WHERE user_id=? AND conversation_id=? AND task_scope=?",
                    (user_id, conversation_id, task_scope),
                )

    def delete_conversation(self, scope: ContextScope) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE user_id=? AND conversation_id=? AND task_scope=?",
                self._key(scope),
            )
        return cursor.rowcount > 0


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_task(self, record: dict[str, Any]) -> None:
        connection_values = (
            record["id"], record["request_id"], record["workflow"], record["status"], record["description"],
            record["progress_percent"], json.dumps(record["result"], ensure_ascii=False) if record.get("result") is not None else None,
            record.get("error"), _iso(record["created_at"]), _iso(record.get("started_at")), _iso(record.get("completed_at")),
        )
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO tasks(id, request_id, workflow, status, description, progress_percent, result_json, error, created_at, started_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "request_id=excluded.request_id, workflow=excluded.workflow, status=excluded.status, description=excluded.description, "
                "progress_percent=excluded.progress_percent, result_json=excluded.result_json, error=excluded.error, "
                "started_at=excluded.started_at, completed_at=excluded.completed_at",
                connection_values,
            )

    @staticmethod
    def _task(row) -> dict[str, Any]:
        item = dict(row)
        result_json = item.pop("result_json")
        item["result"] = json.loads(result_json) if result_json is not None else None
        return item

    def get_task(self, task_id: UUID | str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (str(task_id),)).fetchone()
        return self._task(row) if row else None

    def list_tasks(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._task(row) for row in rows]

    def delete_task(self, task_id: UUID | str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id=?", (str(task_id),))
        return cursor.rowcount > 0

    def save_event(self, event: dict[str, Any]) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO task_events(task_id, sequence, event_id, kind, payload_json, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event["task_id"], event["sequence"], event["event_id"], event["kind"],
                    json.dumps(event["payload"], ensure_ascii=False), _iso(event["occurred_at"]),
                ),
            )
            connection.execute(
                "DELETE FROM task_events WHERE task_id=? AND sequence <= "
                "(SELECT MAX(sequence) - 200 FROM task_events WHERE task_id=?)",
                (event["task_id"], event["task_id"]),
            )

    def list_events(self, task_id: UUID | str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM task_events WHERE task_id=? ORDER BY sequence", (str(task_id),)).fetchall()
        return [
            {
                "event_id": row["event_id"], "task_id": row["task_id"], "sequence": row["sequence"],
                "kind": row["kind"], "payload": json.loads(row["payload_json"]), "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def save_checkpoint(self, checkpoint: TaskCheckpointRecord) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO task_checkpoints(id, task_id, name, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(checkpoint.id), str(checkpoint.task_id), checkpoint.name,
                 json.dumps(checkpoint.payload, ensure_ascii=False, default=str), checkpoint.created_at.isoformat()),
            )

    def list_checkpoints(self, task_id: UUID | str) -> list[TaskCheckpointRecord]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM task_checkpoints WHERE task_id=? ORDER BY created_at, id", (str(task_id),)
            ).fetchall()
        return [
            TaskCheckpointRecord(
                id=row["id"], task_id=row["task_id"], name=row["name"],
                payload=json.loads(row["payload_json"]), created_at=row["created_at"],
            )
            for row in rows
        ]


class MemoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, record: MemoryRecord) -> MemoryRecord:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO memories(id, user_id, content, tags_json, importance, source_conversation_id, source_task_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(record.id), record.user_id, record.content, json.dumps(record.tags, ensure_ascii=False), record.importance,
                 str(record.source_conversation_id) if record.source_conversation_id else None,
                 str(record.source_task_id) if record.source_task_id else None, record.created_at.isoformat()),
            )
        return record

    @staticmethod
    def _memory(row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"], user_id=row["user_id"], content=row["content"], tags=json.loads(row["tags_json"]),
            importance=row["importance"], source_conversation_id=row["source_conversation_id"],
            source_task_id=row["source_task_id"], created_at=row["created_at"],
        )

    def get(self, memory_id: UUID | str, user_id: str) -> MemoryRecord | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM memories WHERE id=? AND user_id=?", (str(memory_id), user_id)).fetchone()
        return self._memory(row) if row else None

    def list_for_user(self, user_id: str, limit: int = 100) -> list[MemoryRecord]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
            ).fetchall()
        return [self._memory(row) for row in rows]

    def delete(self, memory_id: UUID | str, user_id: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id=? AND user_id=?", (str(memory_id), user_id))
        return cursor.rowcount > 0

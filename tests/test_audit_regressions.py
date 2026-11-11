"""Regression coverage for verified findings from the project audit."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from backend.agents.messaging import AgentMessageBus
from backend.agents.registry import AgentRegistry
from backend.api.errors import http_error_handler
from backend.api.schemas import TaskDetailResponse
from backend.core.model_router import completion_text
from backend.database.models import MemoryRecord
from backend.memory.retrieval import rank_memories
from backend.mcp.client import MCPStdioClient
from backend.orchestration.graph import GraphStep, WorkflowGraph
from backend.rag.models import RagChunk
from starlette.exceptions import HTTPException


class AuditRegressionTests(unittest.TestCase):
    def test_memory_ranking_accepts_legacy_naive_timestamps(self) -> None:
        memory = MemoryRecord(user_id="local", content="remember the blue bicycle", created_at=datetime(2025, 1, 1))
        self.assertEqual(rank_memories("blue bicycle", [memory]), [memory])

    def test_task_detail_allows_missing_created_at(self) -> None:
        payload = {
            "id": uuid4(), "status": "queued", "description": "legacy task", "workflow": "research",
            "progress_percent": 0, "request_id": uuid4(), "created_at": None,
        }
        self.assertIsNone(TaskDetailResponse.model_validate(payload).created_at)

    def test_empty_model_choices_raise_a_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "no choices"):
            completion_text(SimpleNamespace(choices=[]))

    def test_workflow_rejects_invalid_progress_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            WorkflowGraph([GraphStep("researcher", "research", 10, 60), GraphStep("reviewer", "review", 55, 95)])
        with self.assertRaisesRegex(ValueError, "between 0 and 99"):
            WorkflowGraph([GraphStep("researcher", "research", 10, 100)])

    def test_registry_factory_accepts_an_optional_message_bus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agents.yaml"
            path.write_text(
                "agents:\n  - name: researcher\n    description: Research agent\n    model_role: chat\n",
                encoding="utf-8",
            )
            bus = AgentMessageBus()
            registry = AgentRegistry.from_yaml(path, message_bus=bus)
        self.assertIs(registry.message_bus, bus)


class HTTPErrorCodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_413_codes_distinguish_context_from_upload_size(self) -> None:
        request_id = uuid4()
        scope = {"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}
        from starlette.requests import Request

        request = Request(scope)
        request.state.request_id = request_id
        cases = [
            ("Context window limit exceeded", "context_window_exceeded"),
            ("Image exceeds the configured size limit", "payload_too_large"),
        ]
        for detail, expected in cases:
            response = await http_error_handler(request, HTTPException(status_code=413, detail=detail))
            self.assertEqual(json.loads(response.body)["error"]["code"], expected)


class KnowledgeCitationTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_returns_only_sources_cited_by_the_model(self) -> None:
        from unittest.mock import AsyncMock, patch

        from backend.api.routes.knowledge import answer_from_knowledge
        from backend.api.schemas import KnowledgeAnswerRequest

        first_id, second_id = str(uuid4()), str(uuid4())
        chunks = [
            (RagChunk(1, first_id, "first.txt", "first.txt", "first evidence", None, 1, 1, {}), 0.9),
            (RagChunk(2, second_id, "second.txt", "second.txt", "second evidence", None, 1, 1, {}), 0.8),
        ]

        class Router:
            async def complete(self, *_args, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="Supported by [S2]."))],
                    model="test-model",
                )

        service = SimpleNamespace(search=lambda *_args: chunks)
        request = SimpleNamespace(
            state=SimpleNamespace(request_id=uuid4()),
            app=SimpleNamespace(state=SimpleNamespace(rag_service=service)),
        )
        with patch("backend.api.routes.knowledge.run_in_threadpool", new=AsyncMock(return_value=chunks)):
            result = await answer_from_knowledge(KnowledgeAnswerRequest(query="question"), request, Router())
        self.assertEqual([citation.label for citation in result.citations], ["S2"])
        self.assertEqual(result.citations[0].source_id, UUID(second_id))


class MCPRestartTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_restarts_a_crashed_server_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "mcp_stub.py"
            script.write_text(
                "import json, sys\n"
                "for line in sys.stdin:\n"
                "    message = json.loads(line)\n"
                "    if 'id' in message:\n"
                "        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{'ok':True}}), flush=True)\n",
                encoding="utf-8",
            )
            client = MCPStdioClient(sys.executable, [str(script)])
            try:
                first = await client.call_tool("probe", {})
                old_process = client._process
                assert old_process is not None
                old_process.terminate()
                await old_process.wait()
                second = await client.call_tool("probe", {})
                self.assertEqual(first, {"ok": True})
                self.assertEqual(second, {"ok": True})
                self.assertIsNot(client._process, old_process)
            finally:
                await client.close()


if __name__ == "__main__":
    unittest.main()

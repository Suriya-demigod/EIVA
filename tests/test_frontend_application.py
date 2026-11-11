"""Frontend serving and approval API checks for M12."""

import unittest
import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import app
from backend.orchestration.events import TaskEventBus
from backend.tools.approvals import ApprovalManager
from backend.core.permission_manager import PermissionManager, ToolPolicy, PermissionDenied
from backend.tools.gateway import MCPServerSpec, ToolBinding, ToolGateway


class FrontendApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_main_app_and_voice_page_are_served(self) -> None:
        root = self.client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn("EIVA — Personal assistant", root.text)
        self.assertEqual(self.client.get("/app.js").status_code, 200)
        self.assertEqual(self.client.get("/styles.css").status_code, 200)
        voice = self.client.get("/voice-ui/")
        self.assertEqual(voice.status_code, 200)
        self.assertIn("Talk to EIVA", voice.text)
        self.assertEqual(self.client.get("/voice-ui/voice.js").status_code, 200)

    def test_approval_decision_updates_task_event_and_queue(self) -> None:
        app.state.approval_manager = ApprovalManager()
        app.state.event_bus = TaskEventBus()
        task_id, request_id = uuid4(), uuid4()
        approval = app.state.approval_manager.request(
            "filesystem.write_file", task_id, request_id, "Write file at workspace/notes.md? Contents are hidden."
        )

        pending = self.client.get("/api/v1/approvals")
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()["items"][0]["id"], str(approval.id))
        response = self.client.post(f"/api/v1/approvals/{approval.id}", json={"approved": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "approved")
        self.assertEqual(self.client.get("/api/v1/approvals").json()["items"], [])
        events = app.state.event_bus.history(task_id)
        self.assertEqual(events[-1].kind, "approval.decided")
        self.assertEqual(events[-1].payload["status"], "approved")
        self.assertEqual(self.client.post(f"/api/v1/approvals/{approval.id}", json={"approved": False}).status_code, 409)


class ApprovalGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_approval_pauses_tool_then_runs_only_after_decision(self) -> None:
        task_id, request_id = uuid4(), uuid4()
        approvals = ApprovalManager()
        events = TaskEventBus()

        class FakeClient:
            calls = []
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return {"content": [{"type": "text", "text": "written"}]}
            async def close(self):
                return None

        client = FakeClient()
        gateway = ToolGateway(
            {"filesystem.write_file": ToolBinding(server="filesystem", mcp_tool="write_file", input_model="filesystem_write_file")},
            {"filesystem": MCPServerSpec(command="fake")},
            PermissionManager({"filesystem.write_file": ToolPolicy(enabled=True, requires_approval=True, allowed_roots=[str(Path.cwd())])}),
            approval_manager=approvals,
            task_event_sink=events.publish,
        )
        gateway._clients["filesystem"] = client
        operation = asyncio.create_task(gateway.call(
            "filesystem.write_file",
            {"path": str(Path.cwd() / "approval-check.txt"), "content": "sensitive body hidden"},
            task_id=task_id,
            request_id=request_id,
        ))
        for _ in range(100):
            pending = approvals.pending()
            if pending:
                break
            await asyncio.sleep(0)
        self.assertEqual(len(pending), 1)
        self.assertIn("approval-check.txt", pending[0].summary)
        self.assertNotIn("sensitive body", pending[0].summary)
        self.assertEqual(client.calls, [])
        approvals.decide(pending[0].id, True)
        result = await asyncio.wait_for(operation, timeout=1)
        self.assertTrue(result["content"])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual([event.kind for event in events.history(task_id)], ["approval.requested"])


if __name__ == "__main__":
    unittest.main()

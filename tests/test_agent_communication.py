"""M13 internal message isolation and opt-in A2A checks."""

import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.agents.a2a import A2AClient, A2AError, A2APeer
from backend.agents.base import AgentContext
from backend.agents.messaging import AgentMessage, AgentMessageBus
from backend.config import get_settings
from backend.main import app
from backend.orchestration.events import TaskEventBus
from backend.tasks.manager import TaskStatus


class InternalMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_messages_are_scoped_to_task_and_recipient(self) -> None:
        bus = AgentMessageBus()
        task_id, other_task = uuid4(), uuid4()
        context = AgentContext(
            task_id=task_id,
            request_id=uuid4(),
            agent_name="researcher",
            cancellation_event=asyncio.Event(),
            report_progress=lambda *_: asyncio.sleep(0),
            message_bus=bus,
            known_agents={"researcher", "reviewer"},
        )
        sent = await context.send_message("reviewer", "Please review this scoped note")
        bus.publish(AgentMessage(
            task_id=other_task,
            request_id=uuid4(),
            sender="researcher",
            recipient="reviewer",
            kind="request",
            content="separate task",
        ))
        self.assertEqual(sent.task_id, task_id)
        self.assertEqual([message.content for message in bus.history(task_id)], ["Please review this scoped note"])
        self.assertEqual(bus.history(other_task)[0].task_id, other_task)
        with self.assertRaises(ValueError):
            await context.send_message("unknown", "No route")


class A2AClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_peer_card_auth_and_message_contract(self) -> None:
        requests = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("agent-card.json"):
                return httpx.Response(200, json={
                    "name": "Remote",
                    "protocolVersion": "1.0",
                    "supportedInterfaces": [{
                        "url": "https://peer.example/a2a/v1",
                        "protocolBinding": "HTTP+JSON",
                        "protocolVersion": "1.0",
                    }],
                    "securitySchemes": {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
                })
            return httpx.Response(200, json={"task": {"id": "remote-task"}})

        client = A2AClient(
            {"trusted_peer": A2APeer(card_url="https://peer.example/.well-known/agent-card.json", token_env="EIVA_TEST_A2A_TOKEN")},
            transport=httpx.MockTransport(handler),
        )
        with patch.dict(os.environ, {"EIVA_TEST_A2A_TOKEN": "test-token"}):
            result = await client.send_message("trusted_peer", "hello peer", str(uuid4()))
        self.assertEqual(result["task"]["id"], "remote-task")
        self.assertEqual(requests[1].headers["authorization"], "Bearer test-token")
        self.assertEqual(requests[1].headers["a2a-version"], "1.0")
        self.assertEqual(requests[1].url.path, "/a2a/v1/message:send")
        self.assertEqual(json.loads(requests[1].content)["message"]["parts"][0]["text"], "hello peer")

    async def test_peer_network_failure_is_contained(self) -> None:
        async def fail(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unavailable")

        client = A2AClient(
            {"peer": A2APeer(card_url="https://peer.example/.well-known/agent-card.json", token_env="EIVA_TEST_A2A_TOKEN")},
            transport=httpx.MockTransport(fail),
        )
        with patch.dict(os.environ, {"EIVA_TEST_A2A_TOKEN": "test-token"}):
            with self.assertRaisesRegex(A2AError, "communication failed"):
                await client.send_message("peer", "hello", str(uuid4()))

    async def test_http_peer_urls_are_limited_to_loopback(self) -> None:
        with self.assertRaises(ValueError):
            A2APeer(card_url="http://remote.example/card", token_env="EIVA_REMOTE_TOKEN")


class A2AServerTests(unittest.TestCase):
    def test_server_is_hidden_when_disabled_and_requires_bearer_when_enabled(self) -> None:
        disabled = get_settings().model_copy(update={"a2a_enabled": False})
        with patch("backend.api.routes.a2a.get_settings", return_value=disabled):
            client = TestClient(app, raise_server_exceptions=False)
            self.assertEqual(client.get("/.well-known/agent-card.json").status_code, 404)
            self.assertEqual(client.post("/a2a/v1/message:send", json={}).status_code, 404)

        settings = get_settings().model_copy(update={
            "a2a_enabled": True,
            "a2a_server_token": SecretStr("x" * 40),
            "a2a_public_url": "http://127.0.0.1:8000/a2a/v1",
        })
        task_id = uuid4()

        class FakeSupervisor:
            class Tasks:
                def get(self, _):
                    raise AssertionError("task lookup should not run for receive-only tests")

            tasks = Tasks()

            def submit(self, **kwargs):
                self.submitted = kwargs
                return SimpleNamespace(id=task_id, status=TaskStatus.queued)

        event_bus = TaskEventBus()
        message_bus = AgentMessageBus()
        app.state.supervisor = FakeSupervisor()
        app.state.event_bus = event_bus
        app.state.agent_message_bus = message_bus
        with patch("backend.api.routes.a2a.get_settings", return_value=settings):
            client = TestClient(app, raise_server_exceptions=False)
            card = client.get("/.well-known/agent-card.json")
            self.assertEqual(card.status_code, 200)
            self.assertEqual(card.json()["supportedInterfaces"][0]["protocolVersion"], "1.0")
            bad = client.post("/a2a/v1/message:send", json={"message": {"role": "ROLE_USER", "parts": [{"text": "hello"}]}})
            self.assertEqual(bad.status_code, 401)
            accepted = client.post(
                "/a2a/v1/message:send",
                headers={"Authorization": f"Bearer {'x' * 40}", "Content-Type": "application/a2a+json"},
                json={"message": {"role": "ROLE_USER", "messageId": "m-1", "parts": [{"text": "research this"}]}},
            )
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.json()["task"]["status"]["state"], "TASK_STATE_SUBMITTED")
            self.assertEqual(accepted.headers["content-type"], "application/a2a+json")
            self.assertEqual(message_bus.history(task_id)[0].content, "research this")
            self.assertEqual(event_bus.history(task_id)[0].kind, "agent.message.received")
            self.assertNotIn("x" * 40, card.text)

    def test_outbound_dispatch_is_task_scoped_and_traced(self) -> None:
        settings = get_settings().model_copy(update={"a2a_enabled": True})
        task_id = uuid4()

        class Tasks:
            def get(self, received_task_id):
                if received_task_id != task_id:
                    raise LookupError("unknown")
                return SimpleNamespace(id=task_id)

        class FakeClient:
            async def send_message(self, peer, content, message_id):
                self.sent = (peer, content, message_id)
                return {"task": {"id": "peer-task-42"}}

        bus = AgentMessageBus()
        events = TaskEventBus()
        client_impl = FakeClient()
        app.state.supervisor = SimpleNamespace(tasks=Tasks())
        app.state.agent_message_bus = bus
        app.state.event_bus = events
        app.state.a2a_client = client_impl
        with patch("backend.api.routes.a2a.get_settings", return_value=settings):
            response = TestClient(app).post(
                "/api/v1/agent-messages",
                json={"task_id": str(task_id), "peer": "partner", "message": "Review this request"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client_impl.sent[:2], ("partner", "Review this request"))
        self.assertEqual([message.kind for message in bus.history(task_id)], ["request", "response"])
        self.assertEqual([event.kind for event in events.history(task_id)], ["agent.message.sent", "agent.message.received"])


if __name__ == "__main__":
    unittest.main()

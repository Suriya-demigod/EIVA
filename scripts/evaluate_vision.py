"""M11 image and browser-control evaluation with fake model/MCP responses."""

import asyncio
import base64
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
import yaml
from fastapi import FastAPI, Request

from backend.api.routes.vision import router as vision_router
from backend.core.model_router import ModelRouter
from backend.core.permission_manager import PermissionDenied, PermissionManager
from backend.orchestration.events import TaskEventBus
from backend.tools.gateway import MCPServerSpec, ToolBinding, ToolGateway
from backend.tools.schemas import PlaywrightCreateTab, PlaywrightTakeScreenshot, PlaywrightTypeText
from backend.orchestration.graph import WorkflowGraph

ROOT = Path(__file__).resolve().parents[1]
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-png"
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")
FAKE_MCP_SERVER = r'''
import json, sys
marker = sys.argv[1]
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if "id" not in request:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "vision-eval", "version": "1"}}
    elif method == "tools/call":
        params = request.get("params", {})
        with open(marker, "a", encoding="utf-8") as output:
            output.write(json.dumps(params) + "\n")
        if params.get("name") == "browser_take_screenshot":
            content = [{"type": "image", "data": "'''+PNG_B64+r'''", "mimeType": "image/png"}]
        else:
            content = [{"type": "text", "text": json.dumps(params)}]
        result = {"content": content, "isError": False}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
'''
CANCEL_MCP_SERVER = r'''
import json, sys, time
marker = sys.argv[1]
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if "id" not in request:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "cancel-eval", "version": "1"}}
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
    elif method == "tools/call":
        open(marker, "w", encoding="utf-8").write("started")
        time.sleep(60)
'''


class FakeVisionRouter:
    def __init__(self) -> None:
        self.images: list[tuple[str, bytes, str, object]] = []

    async def analyze_image(self, question: str, data: bytes, mime_type: str, request_id=None):
        self.images.append((question, data, mime_type, request_id))
        return "A simple test image.", "qwen/qwen3.8-27b"


class FakeVisionClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.request = None

    async def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            model="qwen/qwen3.8-27b",
            choices=[SimpleNamespace(message=SimpleNamespace(content="A simple test image."))],
        )


class FakeTools:
    def __init__(self) -> None:
        self.calls = []
        self.deny = False

    async def call(self, name, arguments, **kwargs):
        self.calls.append((name, arguments, kwargs))
        if self.deny:
            raise PermissionDenied("test denial")
        return {"content": [{"type": "image", "data": PNG_B64, "mimeType": "image/png"}]}

    async def close_task(self, task_id):
        return None


class FakeSupervisor:
    def __init__(self) -> None:
        self.task_ids = set()
        self.tools = FakeTools()
        self.events = TaskEventBus()
        self.published = []
        original_publish = self.events.publish

        def record_publish(task_id, kind, payload):
            self.published.append((task_id, kind, payload))
            return original_publish(task_id, kind, payload)

        self.events.publish = record_publish

        class Tasks:
            def __init__(self, parent):
                self.parent = parent

            def get(self, task_id):
                if task_id not in self.parent.task_ids:
                    from backend.tasks.manager import TaskNotFound
                    raise TaskNotFound(str(task_id))
                return SimpleNamespace(id=task_id)

        self.tasks = Tasks(self)


async def evaluate_vision_api() -> None:
    app = FastAPI()
    app.include_router(vision_router, prefix="/api/v1")
    supervisor = FakeSupervisor()
    app.state.supervisor = supervisor
    fake_model = FakeVisionRouter()
    app.dependency_overrides[__import__("backend.core.model_router", fromlist=["get_model_router"]).get_model_router] = lambda: fake_model

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid4()
        return await call_next(request)

    settings = SimpleNamespace(vision_max_image_bytes=32)
    with patch("backend.api.routes.vision.get_settings", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://eiva.test"
        ) as client:
            bad_type = await client.post(
                "/api/v1/vision/analyze?question=describe", content=b"x", headers={"content-type": "text/plain"}
            )
            assert bad_type.status_code == 415
            bad_signature = await client.post(
                "/api/v1/vision/analyze?question=describe", content=b"nope", headers={"content-type": "image/png"}
            )
            assert bad_signature.status_code == 415
            oversized = await client.post(
                "/api/v1/vision/analyze?question=describe", content=PNG_BYTES * 10, headers={"content-type": "image/png"}
            )
            assert oversized.status_code == 413
            analyzed = await client.post(
                "/api/v1/vision/analyze?question=Describe+the+image",
                content=PNG_BYTES,
                headers={"content-type": "image/png"},
            )
            assert analyzed.status_code == 200 and analyzed.json()["answer"] == "A simple test image."
            assert fake_model.images[-1][:3] == ("Describe the image", PNG_BYTES, "image/png")

            task_id = uuid4()
            supervisor.task_ids.add(task_id)
            screen = await client.post(
                "/api/v1/vision/screen",
                json={"task_id": str(task_id), "question": "What is on this page?"},
            )
            assert screen.status_code == 200 and screen.json()["model"] == "qwen/qwen3.8-27b"
            assert supervisor.tools.calls[-1][0] == "playwright.take_screenshot"
            assert supervisor.tools.calls[-1][2]["task_id"] == task_id
            assert [event[1] for event in supervisor.published] == [
                "vision.screenshot_started", "vision.screenshot_analyzed"
            ]

            supervisor.tools.deny = True
            denied = await client.post(
                "/api/v1/vision/screen",
                json={"task_id": str(task_id), "question": "Describe it"},
            )
            assert denied.status_code == 403
            missing_task = await client.post(
                "/api/v1/vision/screen",
                json={"task_id": str(uuid4()), "question": "Describe it"},
            )
            assert missing_task.status_code == 404


async def evaluate_shared_model_router() -> None:
    client = FakeVisionClient()
    router = ModelRouter(client, {"vision": "qwen/qwen3.8-27b"})
    answer, model = await router.analyze_image("Describe", PNG_BYTES, "image/png", uuid4())
    assert answer == "A simple test image." and model == "qwen/qwen3.8-27b"
    message = client.request["messages"][0]["content"]
    assert message[0] == {"type": "text", "text": "Describe"}
    assert message[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert client.request["model"] == "qwen/qwen3.8-27b"


async def evaluate_browser_gateway() -> None:
    with TemporaryDirectory(prefix="eiva-m11-") as temp:
        marker = Path(temp) / "calls.jsonl"
        bindings_data = yaml.safe_load((ROOT / "config/tool_bindings.yaml").read_text(encoding="utf-8"))["tools"]
        bindings = {name: ToolBinding.model_validate(item) for name, item in bindings_data.items()}
        server = MCPServerSpec(command=sys.executable, args=["-u", "-c", FAKE_MCP_SERVER, str(marker)])
        servers = {"playwright": server}
        permissions = PermissionManager.from_yaml(ROOT / "config/permissions.yaml")

        def approve(approval_id, tool_name, task_id, request_id):
            return approval_id == f"ok:{tool_name}" and task_id is not None and request_id is not None

        gateway = ToolGateway(bindings, servers, permissions, approval_checker=approve)
        task_id = uuid4()
        request_id = uuid4()
        listed = await gateway.call("playwright.list_tabs", {}, task_id=task_id, request_id=request_id)
        assert json.loads(listed["content"][0]["text"])["arguments"] == {"action": "list"}
        screenshot = await gateway.call(
            "playwright.take_screenshot", {}, task_id=task_id, request_id=request_id
        )
        assert screenshot["content"][0]["type"] == "image"
        denied = False
        try:
            await gateway.call(
                "playwright.type_text", {"target": "e4", "text": "secret"},
                task_id=task_id, request_id=request_id,
            )
        except PermissionDenied:
            denied = True
        assert denied
        denied_without_scope = False
        try:
            await gateway.call("playwright.list_tabs", {}, request_id=request_id)
        except PermissionDenied:
            denied_without_scope = True
        assert denied_without_scope

        typed = await gateway.call(
            "playwright.type_text", {"target": "e4", "text": "hello"},
            task_id=task_id, request_id=request_id, approval_id="ok:playwright.type_text",
        )
        typed_args = json.loads(typed["content"][0]["text"])["arguments"]
        assert typed_args == {"target": "e4", "text": "hello", "submit": False}
        selected = await gateway.call(
            "playwright.select_tab", {"index": 1}, task_id=task_id, request_id=request_id,
            approval_id="ok:playwright.select_tab",
        )
        selected_args = json.loads(selected["content"][0]["text"])["arguments"]
        assert selected_args == {"action": "select", "index": 1}

        assert all(event.task_id == task_id for event in gateway.audit_events(task_id))
        assert any(event.reason == "task_scope_required" for event in gateway.audit_events())
        call_lines = [json.loads(line) for line in marker.read_text(encoding="utf-8").splitlines()]
        called_tools = [line["name"] for line in call_lines]
        assert called_tools == ["browser_tabs", "browser_take_screenshot", "browser_type", "browser_tabs"]
        summarized = WorkflowGraph._bounded_result(screenshot)
        serialized = json.dumps(summarized)
        assert PNG_B64 not in serialized and summarized["image_data_omitted_from_task_record"]
        await gateway.close_task(task_id)
        assert not any(key == f"playwright:{task_id}" for key in gateway._clients)
        await gateway.close()


async def evaluate_cancellation_cleanup() -> None:
    with TemporaryDirectory(prefix="eiva-m11-cancel-") as temp:
        marker = Path(temp) / "started.txt"
        binding = ToolBinding(server="playwright", mcp_tool="browser_press_key", input_model="playwright_press_key")
        permissions = PermissionManager({"playwright.press_key": SimpleNamespace(enabled=True, requires_approval=True, allowed_roots=[])})
        gateway = ToolGateway(
            {"playwright.press_key": binding},
            {"playwright": MCPServerSpec(command=sys.executable, args=["-u", "-c", CANCEL_MCP_SERVER, str(marker)])},
            permissions,
            approval_checker=lambda approval_id, tool, task, request: True,
        )
        task_id = uuid4()
        request_id = uuid4()
        call = asyncio.create_task(
            gateway.call(
                "playwright.press_key", {"key": "Escape"}, task_id=task_id, request_id=request_id,
                approval_id="approved",
            )
        )
        for _ in range(300):
            if marker.exists():
                break
            await asyncio.sleep(0.01)
        assert marker.exists(), "Fake browser action did not start"
        call.cancel()
        try:
            await call
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Cancelling a browser action did not cancel the tool call")
        assert not gateway._clients
        assert gateway.audit_events(task_id)[-1].outcome == "cancelled"
        assert gateway.audit_events(task_id)[-1].reason == "task_cancelled"
        await gateway.close()


async def main() -> None:
    assert PlaywrightTakeScreenshot.model_validate({}).model_dump(by_alias=True) == {
        "target": None, "type": "png", "fullPage": False
    }
    assert PlaywrightCreateTab.model_validate({"url": "https://example.test"}).model_dump(
        exclude_none=True, by_alias=True
    ) == {"action": "new", "url": "https://example.test"}
    assert PlaywrightTypeText.model_validate({"target": "e1", "text": "safe text"}).text == "safe text"
    await evaluate_shared_model_router()
    await evaluate_vision_api()
    await evaluate_browser_gateway()
    await evaluate_cancellation_cleanup()
    print("vision_image_validation_and_shared_groq_model_call=passed")
    print("task_scoped_screenshot_and_action_trace=passed")
    print("browser_tool_permissions_and_argument_mapping=passed")
    print("task_cancellation_closes_browser_mcp_client=passed")
    print("screenshot_data_excluded_from_persistent_task_results=passed")


if __name__ == "__main__":
    asyncio.run(main())

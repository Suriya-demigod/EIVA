"""Local async integration evaluation for EIVA milestones M00-M07.

Uses fake agents and a local fake MCP stdio process. It does not call Groq,
GitHub, browser websites, or write through the configured filesystem tools.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import yaml
from fastapi import FastAPI, Request

from backend.agents.base import AgentContext, AgentDefinition, AgentInput, AgentOutput, BaseAgent
from backend.agents.model_agent import ModelAgent
from backend.agents.registry import AgentExecutionError, AgentRegistry
from backend.api.routes.tasks import router as task_router
from backend.core.permission_manager import PermissionDenied, PermissionManager
from backend.orchestration.events import TaskEventBus
from backend.orchestration.graph import ToolRequest
from backend.orchestration.supervisor import WorkflowSupervisor
from backend.skills.registry import SkillRegistry
from backend.tasks.manager import TaskManager, TaskStatus
from backend.tools.gateway import MCPServerSpec, ToolBinding, ToolExecutionFailure, ToolGateway


ROOT = Path(__file__).resolve().parents[1]
FAKE_MCP_SERVER = r'''
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if "id" not in request:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "eiva-eval", "version": "1"}}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "fixture-result"}], "isError": False}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
'''


class AgentTracker:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0
        self.delay = 0.0
        self.fail_agent: str | None = None
        self.block_agent: str | None = None
        self.block_started = asyncio.Event()
        self.release = asyncio.Event()


class EvaluationAgent(BaseAgent):
    def __init__(self, definition: AgentDefinition, tracker: AgentTracker) -> None:
        super().__init__(definition)
        self.tracker = tracker

    async def run(self, payload: AgentInput, context: AgentContext) -> AgentOutput:
        tracker = self.tracker
        tracker.active += 1
        tracker.maximum = max(tracker.maximum, tracker.active)
        try:
            await context.report_progress(f"{self.definition.name} active", 30)
            if tracker.fail_agent == self.definition.name:
                raise RuntimeError("private test detail")
            if tracker.block_agent == self.definition.name:
                tracker.block_started.set()
                await tracker.release.wait()
            if tracker.delay:
                await asyncio.sleep(tracker.delay)
            return AgentOutput(
                message=f"{self.definition.name} completed",
                data={"received_context": payload.context},
            )
        finally:
            tracker.active -= 1


class EvaluationTools:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call(self, name: str, arguments: dict, **kwargs):
        self.calls.append(name)
        if name == "fake.denied":
            raise PermissionDenied("approval required")
        return {"content": [{"type": "text", "text": "tool fixture"}]}


def build_agents(tracker: AgentTracker) -> AgentRegistry:
    skills = SkillRegistry.from_directory(ROOT / "backend/skills/available")
    registry = AgentRegistry.from_yaml(ROOT / "config/agents.yaml", skills)
    for definition, _ in registry.definitions():
        registry.register(EvaluationAgent(definition, tracker))
    return registry


async def wait_for_status(manager: TaskManager, task_id, expected: TaskStatus, timeout: float = 4):
    async def poll():
        while manager.get(task_id).status != expected:
            await asyncio.sleep(0.005)
        return manager.get(task_id)

    return await asyncio.wait_for(poll(), timeout)


async def check_mcp_gateway(task_id):
    binding_data = yaml.safe_load((ROOT / "config/tool_bindings.yaml").read_text(encoding="utf-8"))["tools"]
    bindings = {name: ToolBinding.model_validate(value) for name, value in binding_data.items()}
    server = MCPServerSpec(command=sys.executable, args=["-u", "-c", FAKE_MCP_SERVER])
    servers = {name: server for name in ("filesystem", "github", "playwright")}
    permissions = PermissionManager.from_yaml(ROOT / "config/permissions.yaml")
    gateway = ToolGateway(bindings, servers, permissions)
    result = await gateway.call(
        "filesystem.read_file",
        {"path": str(ROOT / "README.md")},
        task_id=task_id,
        request_id=uuid4(),
    )
    assert result["content"][0]["text"] == "fixture-result"
    safe_reads = [
        ("filesystem.list_directory", {"path": str(ROOT)}),
        ("github.get_file", {"owner": "example", "repo": "eiva", "path": "README.md"}),
        ("github.read_issue", {"owner": "example", "repo": "eiva", "issue_number": 1}),
        ("playwright.snapshot", {}),
    ]
    for tool_name, arguments in safe_reads:
        read_result = await gateway.call(tool_name, arguments, task_id=task_id, request_id=uuid4())
        assert read_result["content"][0]["text"] == "fixture-result"
    try:
        await gateway.call(
            "filesystem.write_file",
            {"path": str(ROOT / "README.md"), "content": "must not run"},
            task_id=task_id,
            request_id=uuid4(),
        )
    except PermissionDenied:
        pass
    else:
        raise AssertionError("Write call without a verified approval was not denied")
    assert [event.outcome for event in gateway.audit_events(task_id)] == [
        "allowed", "allowed", "allowed", "allowed", "allowed", "denied"
    ]
    await gateway.close()

    approval_calls = []

    def approve_fixture(approval_id, tool_name, approved_task_id, request_id):
        approval_calls.append((tool_name, approved_task_id, request_id))
        return approval_id == f"grant:{tool_name}" and approved_task_id == task_id and request_id is not None

    approved_gateway = ToolGateway(bindings, servers, permissions, approval_checker=approve_fixture)
    approved_writes = [
        ("filesystem.write_file", {"path": str(ROOT / "README.md"), "content": "fixture only"}),
        ("github.create_issue", {"owner": "example", "repo": "eiva", "title": "test"}),
        ("playwright.navigate", {"url": "https://example.invalid"}),
        ("playwright.click", {"target": "example button"}),
    ]
    for tool_name, arguments in approved_writes:
        write_result = await approved_gateway.call(
            tool_name,
            arguments,
            task_id=task_id,
            request_id=uuid4(),
            approval_id=f"grant:{tool_name}",
        )
        assert write_result["content"][0]["text"] == "fixture-result"
    assert len(approval_calls) == len(approved_writes)
    await approved_gateway.close()

    unavailable = ToolGateway(bindings, {}, PermissionManager.from_yaml(ROOT / "config/permissions.yaml"))
    try:
        await unavailable.call("filesystem.read_file", {"path": str(ROOT / "README.md")}, task_id=task_id)
    except ToolExecutionFailure as exc:
        assert exc.error_type == "MCPUnavailableError"
    else:
        raise AssertionError("An unconfigured MCP server was not contained as unavailable")


async def check_agent_runtime_and_skill_prompts():
    definitions = [
        AgentDefinition(name="timeout_probe", description="timeout test", model_role="researcher", timeout_seconds=0.02),
    ]

    class SlowAgent(BaseAgent):
        async def run(self, payload, context):
            await asyncio.sleep(1)
            return AgentOutput(message="too late")

    registry = AgentRegistry(definitions)
    registry.register(SlowAgent(definitions[0]))
    timeout_events = []
    try:
        await registry.invoke(
            "timeout_probe",
            AgentInput(task="time out"),
            task_id=uuid4(),
            request_id=uuid4(),
            event_sink=timeout_events.append,
        )
    except AgentExecutionError as exc:
        assert exc.error_type == "timeout"
    else:
        raise AssertionError("Agent timeout was not enforced")
    assert [event.kind for event in timeout_events] == ["started", "failed"]

    skills = SkillRegistry.from_directory(ROOT / "backend/skills/available")
    definition = next(item for item, _ in AgentRegistry.from_yaml(ROOT / "config/agents.yaml", skills).definitions() if item.name == "researcher")

    class FakeRouter:
        messages = None

        async def complete(self, role, messages, **options):
            self.messages = messages
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="fake model response"))])

    fake_router = FakeRouter()

    async def report_progress(message, progress):
        return None

    context = AgentContext(
        task_id=uuid4(),
        request_id=uuid4(),
        agent_name="researcher",
        cancellation_event=asyncio.Event(),
        report_progress=report_progress,
    )
    agent = ModelAgent(definition, skills, fake_router)
    output = await agent.run(AgentInput(task="summarize supplied notes"), context)
    system_prompt = fake_router.messages[0]["content"]
    assert output.message == "fake model response"
    assert "Skill: web_research" in system_prompt and "Skill: document_analysis" in system_prompt
    assert "Skill: code_debugging" not in system_prompt



async def check_workflows_and_events():
    tracker = AgentTracker()
    event_bus = TaskEventBus()
    manager = TaskManager(event_bus)
    tools = EvaluationTools()
    supervisor = WorkflowSupervisor(manager, event_bus, build_agents(tracker), tools, max_concurrent=1)

    research = supervisor.submit(
        workflow="research",
        description="Compare two designs",
        tool_requests=[ToolRequest("fake.read", {"path": "fixture"})],
        request_id=uuid4(),
    )
    completed = await wait_for_status(manager, research.id, TaskStatus.completed)
    assert completed.progress_percent == 100
    assert [item["agent_name"] for item in completed.result["agent_outputs"]] == ["researcher", "reviewer"]
    assert completed.result["tool_results"][0]["result"]["content"][0]["text"] == "tool fixture"
    kinds = [event.kind for event in event_bus.history(research.id)]
    assert "agent.handoff" in kinds and "agent.progress" in kinds and "tool.completed" in kinds and "task.completed" in kinds

    coding = supervisor.submit(
        workflow="coding",
        description="Inspect a patch",
        tool_requests=[ToolRequest("fake.denied", {})],
        request_id=uuid4(),
    )
    failed_tool = await wait_for_status(manager, coding.id, TaskStatus.completed)
    assert failed_tool.result["tool_results"][0]["error"] == "PermissionDenied"
    assert any(event.kind == "tool.failed" for event in event_bus.history(coding.id))

    tracker.fail_agent = "researcher"
    failing = supervisor.submit(workflow="research", description="fails safely", tool_requests=[], request_id=uuid4())
    failed = await wait_for_status(manager, failing.id, TaskStatus.failed)
    assert "AgentExecutionError" in failed.error and "private test detail" not in failed.error
    tracker.fail_agent = None

    tracker.block_agent = "researcher"
    tracker.block_started = asyncio.Event()
    cancelling = supervisor.submit(workflow="research", description="cancel me", tool_requests=[], request_id=uuid4())
    await asyncio.wait_for(tracker.block_started.wait(), 2)
    manager.cancel(cancelling.id)
    cancelled = await wait_for_status(manager, cancelling.id, TaskStatus.cancelled)
    assert cancelled.error == "Task cancelled by the user"
    assert any(event.kind == "agent.cancelled" for event in event_bus.history(cancelling.id))
    tracker.block_agent = None
    tracker.release.set()

    tracker.delay = 0.015
    before = tracker.maximum
    left = supervisor.submit(workflow="coding", description="one", tool_requests=[], request_id=uuid4())
    right = supervisor.submit(workflow="coding", description="two", tool_requests=[], request_id=uuid4())
    await wait_for_status(manager, left.id, TaskStatus.completed)
    await wait_for_status(manager, right.id, TaskStatus.completed)
    assert tracker.maximum <= 1 and tracker.maximum >= before
    return manager, event_bus, supervisor


async def check_task_api():
    tracker = AgentTracker()
    events = TaskEventBus()
    manager = TaskManager(events)
    supervisor = WorkflowSupervisor(manager, events, build_agents(tracker), EvaluationTools(), max_concurrent=2)
    app = FastAPI()
    app.include_router(task_router, prefix="/api/v1")

    @app.middleware("http")
    async def set_request_id(request: Request, call_next):
        request.state.request_id = uuid4()
        return await call_next(request)

    app.state.supervisor = supervisor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://eiva.test") as client:
        response = await client.post(
            "/api/v1/tasks",
            json={"workflow": "research", "description": "API evaluation", "tool_calls": []},
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["id"]
        await wait_for_status(manager, UUID(task_id), TaskStatus.completed)
        detail = await client.get(f"/api/v1/tasks/{task_id}")
        assert detail.status_code == 200 and detail.json()["status"] == "completed"
        listing = await client.get("/api/v1/tasks")
        assert listing.status_code == 200 and len(listing.json()["items"]) == 1
        stream = await client.get(f"/api/v1/tasks/{task_id}/events")
        assert stream.status_code == 200 and "task.completed" in stream.text

        tracker.block_agent = "researcher"
        tracker.block_started = asyncio.Event()
        cancel_response = await client.post(
            "/api/v1/tasks",
            json={"workflow": "research", "description": "API cancellation", "tool_calls": []},
        )
        assert cancel_response.status_code == 202
        cancel_id = UUID(cancel_response.json()["id"])
        await asyncio.wait_for(tracker.block_started.wait(), 2)
        cancel_result = await client.post(f"/api/v1/tasks/{cancel_id}/cancel")
        assert cancel_result.status_code == 202
        cancelled = await wait_for_status(manager, cancel_id, TaskStatus.cancelled)
        assert cancelled.status == TaskStatus.cancelled


async def main() -> None:
    mcp_task_id = uuid4()
    await check_agent_runtime_and_skill_prompts()
    await check_mcp_gateway(mcp_task_id)
    await check_workflows_and_events()
    await check_task_api()
    print("agent_progress_timeout=passed isolated_skill_prompts=passed mcp_stdio=passed gateway_permissions=passed")
    print("research_handoff=passed coding_handoff=passed")
    print("tool_failure_recovery=passed cancellation=passed concurrency_limit=passed task_api_sse=passed")


if __name__ == "__main__":
    asyncio.run(main())

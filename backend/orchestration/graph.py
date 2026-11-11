"""Sequential graph execution with bounded agent and tool handoffs."""

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from backend.agents.base import AgentInput, AgentOutput
from backend.agents.registry import AgentRegistry
from backend.orchestration.events import TaskEventBus
from backend.tasks.manager import TaskManager
from backend.tools.gateway import ToolGateway


MAX_TOOL_CALLS_PER_TASK = 8
MAX_TOOL_RESULT_CHARS = 16_000


@dataclass(frozen=True)
class ToolRequest:
    name: str
    arguments: dict[str, Any]
    approval_id: str | None = None


@dataclass(frozen=True)
class WorkflowResult:
    message: str
    agent_outputs: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]


@dataclass(frozen=True)
class GraphStep:
    agent_name: str
    phase: str
    progress_start: int
    progress_end: int


class WorkflowGraph:
    def __init__(self, steps: list[GraphStep]) -> None:
        if len(steps) < 1:
            raise ValueError("A workflow graph needs at least one step")
        previous_end = -1
        for step in steps:
            if not 0 <= step.progress_start <= step.progress_end <= 99:
                raise ValueError("Workflow step progress must be ordered between 0 and 99")
            if step.progress_start < previous_end:
                raise ValueError("Workflow step progress ranges must not overlap or move backward")
            previous_end = step.progress_end
        self.steps = steps

    async def run(
        self,
        *,
        task_id: UUID,
        request_id: UUID,
        description: str,
        tool_requests: list[ToolRequest],
        agents: AgentRegistry,
        tools: ToolGateway,
        tasks: TaskManager,
        events: TaskEventBus,
    ) -> WorkflowResult:
        if len(tool_requests) > MAX_TOOL_CALLS_PER_TASK:
            raise ValueError(f"A workflow may request at most {MAX_TOOL_CALLS_PER_TASK} tools")

        agent_outputs: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        previous: AgentOutput | None = None
        for index, step in enumerate(self.steps):
            tasks.update_progress(task_id, step.progress_start, step.phase)
            events.publish(task_id, "agent.handoff", {"agent_name": step.agent_name, "phase": step.phase, "step": index + 1})
            prompt = description if previous is None else "Review and improve the preceding agent's work."
            context = {"phase": step.phase}
            if previous is not None:
                context["previous_output"] = previous.model_dump()
            if tool_results:
                context["tool_results"] = tool_results

            async def forward_agent_event(event) -> None:
                events.publish(task_id, f"agent.{event.kind}", event.model_dump(mode="json"))

            invocation = await agents.invoke(
                step.agent_name,
                AgentInput(task=prompt, context=context),
                task_id=task_id,
                request_id=request_id,
                event_sink=forward_agent_event,
            )
            previous = invocation.output
            agent_outputs.append({"agent_name": step.agent_name, **previous.model_dump()})
            tasks.checkpoint(
                task_id,
                f"after-{step.agent_name}",
                {"agent_name": step.agent_name, "output": previous.model_dump(mode="json")},
            )

            if index == 0 and tool_requests:
                tasks.update_progress(task_id, min(99, step.progress_end + 5), "Running explicitly requested tools")
                for tool_request in tool_requests:
                    events.publish(task_id, "tool.started", {"tool_name": tool_request.name})
                    try:
                        result = await tools.call(
                            tool_request.name,
                            tool_request.arguments,
                            task_id=task_id,
                            request_id=request_id,
                            approval_id=tool_request.approval_id,
                        )
                        bounded = self._bounded_result(result)
                        tool_results.append({"tool_name": tool_request.name, "result": bounded})
                        events.publish(task_id, "tool.completed", {"tool_name": tool_request.name})
                    except Exception as exc:
                        error_type = type(exc).__name__
                        tool_results.append({"tool_name": tool_request.name, "error": error_type})
                        events.publish(task_id, "tool.failed", {"tool_name": tool_request.name, "error_type": error_type})

            tasks.update_progress(
                task_id,
                max(step.progress_end, tasks.get(task_id).progress_percent),
                f"Completed {step.phase}",
            )

        return WorkflowResult(
            message=previous.message if previous else "Workflow completed without an agent result",
            agent_outputs=agent_outputs,
            tool_results=tool_results,
        )

    @staticmethod
    def _bounded_result(result: dict[str, Any]) -> Any:
        content = result.get("content")
        if isinstance(content, list) and any(isinstance(item, dict) and item.get("type") == "image" for item in content):
            safe_content = [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"data"}
                }
                if isinstance(item, dict) and item.get("type") == "image"
                else item
                for item in content
            ]
            result = {**result, "content": safe_content, "image_data_omitted_from_task_record": True}
        serialized = json.dumps(result, ensure_ascii=False, default=str)
        if len(serialized) <= MAX_TOOL_RESULT_CHARS:
            return result
        return {"truncated": True, "preview": serialized[:MAX_TOOL_RESULT_CHARS]}

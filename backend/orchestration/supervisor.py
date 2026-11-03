"""Supervisor for bounded research and coding workflows."""

import asyncio
from typing import Any
from uuid import UUID

from backend.agents.registry import AgentRegistry
from backend.orchestration.events import TaskEventBus
from backend.orchestration.graph import ToolRequest, WorkflowGraph
from backend.orchestration.workflows.coding import CODING_GRAPH
from backend.orchestration.workflows.research import RESEARCH_GRAPH
from backend.tasks.manager import TaskManager, TaskRecord, TaskStatus, TERMINAL_STATUSES
from backend.tools.gateway import ToolGateway


WORKFLOWS: dict[str, WorkflowGraph] = {"research": RESEARCH_GRAPH, "coding": CODING_GRAPH}


class WorkflowSupervisor:
    def __init__(
        self,
        tasks: TaskManager,
        events: TaskEventBus,
        agents: AgentRegistry,
        tools: ToolGateway,
        *,
        max_concurrent: int = 4,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be positive")
        self.tasks = tasks
        self.events = events
        self.agents = agents
        self.tools = tools
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def submit(
        self,
        *,
        workflow: str,
        description: str,
        tool_requests: list[ToolRequest],
        request_id: UUID,
    ) -> TaskRecord:
        if workflow not in WORKFLOWS:
            raise ValueError(f"Unsupported workflow '{workflow}'")
        return self.tasks.create(
            workflow,
            description,
            request_id,
            lambda task_id, rid: self._execute(task_id, rid, workflow, description, tool_requests),
        )

    async def _execute(
        self,
        task_id: UUID,
        request_id: UUID,
        workflow: str,
        description: str,
        tool_requests: list[ToolRequest],
    ) -> None:
        try:
            async with self._semaphore:
                record = self.tasks.get(task_id)
                if record.status == TaskStatus.cancelled:
                    return
                self.tasks.transition(task_id, TaskStatus.running)
                graph_result = await WORKFLOWS[workflow].run(
                    task_id=task_id,
                    request_id=request_id,
                    description=description,
                    tool_requests=tool_requests,
                    agents=self.agents,
                    tools=self.tools,
                    tasks=self.tasks,
                    events=self.events,
                )
                self.tasks.set_result(
                    task_id,
                    {
                        "message": graph_result.message,
                        "agent_outputs": graph_result.agent_outputs,
                        "tool_results": graph_result.tool_results,
                    },
                )
                self.tasks.transition(task_id, TaskStatus.completed)
        except asyncio.CancelledError:
            record = self.tasks.get(task_id)
            if record.status not in TERMINAL_STATUSES:
                self.tasks.transition(task_id, TaskStatus.cancelled, error="Task cancelled by the user")
            raise
        except Exception as exc:
            record = self.tasks.get(task_id)
            if record.status not in TERMINAL_STATUSES:
                self.tasks.transition(
                    task_id,
                    TaskStatus.failed,
                    error=f"Workflow '{workflow}' failed ({type(exc).__name__})",
                )


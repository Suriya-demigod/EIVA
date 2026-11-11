"""Config-backed registry and lifecycle runner for EIVA agents."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
import inspect
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from backend.agents.base import (
    AgentContext,
    AgentDefinition,
    AgentEvent,
    AgentEventSink,
    AgentInput,
    AgentOutput,
    BaseAgent,
)
from backend.agents.messaging import AgentMessageBus
from backend.agents.browser import BrowserAgent
from backend.agents.developer import DeveloperAgent
from backend.agents.researcher import ResearcherAgent
from backend.agents.reviewer import ReviewerAgent
from backend.config import get_settings
from backend.skills.registry import SkillRegistry


class UnknownAgentError(LookupError):
    pass


class DuplicateAgentError(ValueError):
    pass


class AgentExecutionError(RuntimeError):
    def __init__(self, agent_name: str, error_type: str) -> None:
        super().__init__(f"Agent '{agent_name}' failed ({error_type})")
        self.agent_name = agent_name
        self.error_type = error_type


@dataclass(frozen=True)
class AgentInvocation:
    output: AgentOutput
    events: list[AgentEvent]


class AgentRegistry:
    def __init__(self, definitions: list[AgentDefinition], message_bus: AgentMessageBus | None = None) -> None:
        self._definitions = {definition.name: definition for definition in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("Agent configuration contains duplicate names")
        self._agents: dict[str, BaseAgent] = {}
        self._active: dict[UUID, tuple[asyncio.Task[AgentOutput] | None, asyncio.Event, str]] = {}
        self.message_bus = message_bus

    @classmethod
    def from_yaml(cls, path: Path, skill_registry: SkillRegistry | None = None) -> "AgentRegistry":
        config: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        definitions = [AgentDefinition.model_validate(item) for item in config.get("agents", [])]
        if not definitions:
            raise ValueError(f"No agent definitions configured in {path}")
        if skill_registry is not None:
            for definition in definitions:
                skill_registry.get_many(definition.skills)
        return cls(definitions)

    def register(self, agent: BaseAgent) -> None:
        name = agent.definition.name
        configured = self._definitions.get(name)
        if configured is None:
            raise UnknownAgentError(f"Agent '{name}' is not configured")
        if name in self._agents:
            raise DuplicateAgentError(f"Agent '{name}' is already registered")
        if configured.model_role != agent.definition.model_role or configured.skills != agent.definition.skills:
            raise ValueError(f"Agent '{name}' role or skill assignments do not match its configuration")
        self._agents[name] = agent

    def definitions(self) -> list[tuple[AgentDefinition, bool]]:
        return [(definition, name in self._agents) for name, definition in self._definitions.items()]

    def get(self, name: str) -> BaseAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            if name not in self._definitions:
                raise UnknownAgentError(f"Agent '{name}' is not configured") from exc
            raise UnknownAgentError(f"Agent '{name}' is configured but not registered yet") from exc

    async def invoke(
        self,
        name: str,
        payload: AgentInput,
        *,
        task_id: UUID,
        request_id: UUID,
        event_sink: AgentEventSink | None = None,
    ) -> AgentInvocation:
        agent = self.get(name)
        if task_id in self._active:
            raise DuplicateAgentError(f"Task '{task_id}' already has an active agent")

        events: list[AgentEvent] = []

        async def emit(kind: str, message: str, progress_percent: int | None = None) -> None:
            event = AgentEvent(
                task_id=task_id,
                request_id=request_id,
                agent_name=name,
                kind=kind,
                message=message,
                progress_percent=progress_percent,
            )
            events.append(event)
            if event_sink is not None:
                result = event_sink(event)
                if inspect.isawaitable(result):
                    await result

        async def report_progress(message: str, progress_percent: int | None) -> None:
            await emit("progress", message, progress_percent)

        cancellation_event = asyncio.Event()
        context = AgentContext(
            task_id=task_id,
            request_id=request_id,
            agent_name=name,
            cancellation_event=cancellation_event,
            report_progress=report_progress,
            message_bus=self.message_bus,
            known_agents=set(self._definitions),
        )
        self._active[task_id] = (None, cancellation_event, name)
        execution: asyncio.Task[AgentOutput] | None = None
        try:
            await emit("started", "Agent started", 0)
            if cancellation_event.is_set():
                raise asyncio.CancelledError

            execution = asyncio.create_task(agent.run(payload, context), name=f"eiva-agent:{name}:{task_id}")
            self._active[task_id] = (execution, cancellation_event, name)
            output = AgentOutput.model_validate(
                await asyncio.wait_for(execution, timeout=agent.definition.timeout_seconds)
            )
        except asyncio.TimeoutError as exc:
            cancellation_event.set()
            await emit("failed", "Agent exceeded its configured time limit")
            raise AgentExecutionError(name, "timeout") from exc
        except asyncio.CancelledError:
            cancellation_event.set()
            if execution is not None and not execution.done():
                execution.cancel()
            await emit("cancelled", "Agent execution was cancelled")
            raise
        except Exception as exc:
            await emit("failed", "Agent execution failed")
            raise AgentExecutionError(name, type(exc).__name__) from exc
        else:
            await emit("completed", "Agent completed", 100)
            return AgentInvocation(output=output, events=events)
        finally:
            self._active.pop(task_id, None)

    async def cancel(self, task_id: UUID) -> bool:
        active = self._active.get(task_id)
        if active is None:
            return False
        execution, cancellation_event, _ = active
        cancellation_event.set()
        if execution is not None:
            execution.cancel()
        return True


@lru_cache
def get_agent_registry() -> AgentRegistry:
    settings = get_settings()
    skill_registry = SkillRegistry.from_directory(Path(settings.skills_config_dir))
    registry = AgentRegistry.from_yaml(Path(settings.agents_config_path), skill_registry)
    agent_classes = {
        "researcher": ResearcherAgent,
        "developer": DeveloperAgent,
        "browser": BrowserAgent,
        "reviewer": ReviewerAgent,
    }
    for definition, _ in registry.definitions():
        agent_class = agent_classes.get(definition.name)
        if agent_class is not None:
            registry.register(agent_class(definition, skill_registry))
    return registry

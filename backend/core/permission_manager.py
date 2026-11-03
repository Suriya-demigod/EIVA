"""Policy decisions and bounded, secret-safe tool audit records."""

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    requires_approval: bool = True
    allowed_roots: list[str] = Field(default_factory=list)


class ToolAuditEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    task_id: UUID | None = None
    request_id: UUID | None = None
    tool_name: str
    outcome: str
    reason: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PermissionDenied(PermissionError):
    pass


class PermissionManager:
    def __init__(self, policies: dict[str, ToolPolicy], *, audit_limit: int = 1000) -> None:
        self._policies = policies
        self._audit: deque[ToolAuditEvent] = deque(maxlen=audit_limit)

    @classmethod
    def from_yaml(cls, path: Path) -> "PermissionManager":
        config: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw = config.get("tools", {})
        base_dir = path.resolve().parent.parent
        policies = {}
        for name, policy_data in raw.items():
            policy = ToolPolicy.model_validate(policy_data)
            policy.allowed_roots = [str((base_dir / root).resolve()) if not Path(root).is_absolute() else str(Path(root).resolve()) for root in policy.allowed_roots]
            policies[name] = policy
        return cls(policies)

    def policy_for(self, tool_name: str) -> ToolPolicy | None:
        return self._policies.get(tool_name)

    def authorize(
        self,
        tool_name: str,
        *,
        approval_verified: bool = False,
        path: str | None = None,
        task_id: UUID | None = None,
        request_id: UUID | None = None,
    ) -> ToolPolicy:
        policy = self._policies.get(tool_name)
        if policy is None or not policy.enabled:
            self.record(tool_name, "denied", "tool_disabled_or_unconfigured", task_id, request_id)
            raise PermissionDenied(f"Tool '{tool_name}' is disabled or unconfigured")
        if policy.requires_approval and not approval_verified:
            self.record(tool_name, "denied", "approval_required", task_id, request_id)
            raise PermissionDenied(f"Tool '{tool_name}' requires verified approval")
        if path is not None:
            resolved_path = Path(path).resolve()
            roots = [Path(root).resolve() for root in policy.allowed_roots]
            if not roots or not any(resolved_path == root or root in resolved_path.parents for root in roots):
                self.record(tool_name, "denied", "path_outside_allowed_roots", task_id, request_id)
                raise PermissionDenied("Filesystem path is outside the configured allowed roots")
        return policy

    def record(
        self,
        tool_name: str,
        outcome: str,
        reason: str,
        task_id: UUID | None = None,
        request_id: UUID | None = None,
    ) -> ToolAuditEvent:
        event = ToolAuditEvent(tool_name=tool_name, outcome=outcome, reason=reason, task_id=task_id, request_id=request_id)
        self._audit.append(event)
        return event

    def audit_events(self, task_id: UUID | None = None) -> list[ToolAuditEvent]:
        events = list(self._audit)
        return [event for event in events if event.task_id == task_id] if task_id is not None else events

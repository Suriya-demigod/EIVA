"""Validate, authorize, execute, and audit configured MCP tool calls."""

import asyncio
import inspect
import os
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError

from backend.core.permission_manager import PermissionDenied, PermissionManager
from backend.mcp.client import MCPStdioClient, MCPUnavailableError
from backend.tools.approvals import ApprovalManager, ApprovalStatus
from backend.tools.schemas import (
    FilesystemListDirectory,
    FilesystemReadFile,
    FilesystemWriteFile,
    GitHubCreateIssue,
    GitHubGetFile,
    GitHubReadIssue,
    PlaywrightClick,
    PlaywrightCloseTab,
    PlaywrightCreateTab,
    PlaywrightListTabs,
    PlaywrightNavigate,
    PlaywrightPressKey,
    PlaywrightSelectTab,
    PlaywrightSnapshot,
    PlaywrightTakeScreenshot,
    PlaywrightTypeText,
)


class MCPServerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class ToolBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server: str
    mcp_tool: str
    input_model: str


class ToolExecutionFailure(RuntimeError):
    def __init__(self, tool_name: str, error_type: str) -> None:
        super().__init__(f"Tool '{tool_name}' failed ({error_type})")
        self.tool_name = tool_name
        self.error_type = error_type


class ToolInputError(ValueError):
    pass


InputModel = type[BaseModel]
APPROVAL_CHECKER = Callable[[str, str, UUID | None, UUID | None], bool | Awaitable[bool]]
INPUT_MODELS: dict[str, InputModel] = {
    "filesystem_read_file": FilesystemReadFile,
    "filesystem_list_directory": FilesystemListDirectory,
    "filesystem_write_file": FilesystemWriteFile,
    "github_get_file": GitHubGetFile,
    "github_read_issue": GitHubReadIssue,
    "github_create_issue": GitHubCreateIssue,
    "playwright_navigate": PlaywrightNavigate,
    "playwright_snapshot": PlaywrightSnapshot,
    "playwright_click": PlaywrightClick,
    "playwright_take_screenshot": PlaywrightTakeScreenshot,
    "playwright_list_tabs": PlaywrightListTabs,
    "playwright_select_tab": PlaywrightSelectTab,
    "playwright_create_tab": PlaywrightCreateTab,
    "playwright_close_tab": PlaywrightCloseTab,
    "playwright_type_text": PlaywrightTypeText,
    "playwright_press_key": PlaywrightPressKey,
}


class ToolGateway:
    def __init__(
        self,
        bindings: dict[str, ToolBinding],
        servers: dict[str, MCPServerSpec],
        permissions: PermissionManager,
        approval_checker: APPROVAL_CHECKER | None = None,
        approval_manager: ApprovalManager | None = None,
        task_event_sink: Callable[[UUID, str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self._bindings = bindings
        self._servers = servers
        self._permissions = permissions
        self._approval_checker = approval_checker
        self._approval_manager = approval_manager
        self._task_event_sink = task_event_sink
        self._clients: dict[str, MCPStdioClient] = {}

    @classmethod
    def from_files(
        cls,
        bindings_path: Path,
        servers_path: Path,
        permissions_path: Path,
        approval_checker: APPROVAL_CHECKER | None = None,
        approval_manager: ApprovalManager | None = None,
        task_event_sink: Callable[[UUID, str, dict[str, Any]], Any] | None = None,
    ) -> "ToolGateway":
        binding_data: Any = yaml.safe_load(bindings_path.read_text(encoding="utf-8")) or {}
        server_data: Any = yaml.safe_load(servers_path.read_text(encoding="utf-8")) or {}
        bindings = {name: ToolBinding.model_validate(item) for name, item in binding_data.get("tools", {}).items()}
        servers = {name: MCPServerSpec.model_validate(item) for name, item in server_data.get("servers", {}).items()}
        for name, binding in bindings.items():
            if binding.input_model not in INPUT_MODELS:
                raise ValueError(f"Tool '{name}' uses unknown input model '{binding.input_model}'")
        return cls(
            bindings,
            servers,
            PermissionManager.from_yaml(permissions_path),
            approval_checker,
            approval_manager,
            task_event_sink,
        )

    async def _is_approved(
        self,
        approval_id: str | None,
        tool_name: str,
        task_id: UUID | None,
        request_id: UUID | None,
    ) -> bool:
        if approval_id is None or self._approval_checker is None:
            return False
        result = self._approval_checker(approval_id, tool_name, task_id, request_id)
        return bool(await result) if inspect.isawaitable(result) else bool(result)

    def tool_names(self) -> list[str]:
        return sorted(self._bindings)

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        task_id: UUID | None = None,
        request_id: UUID | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        binding = self._bindings.get(tool_name)
        if binding is None:
            self._permissions.record(tool_name, "denied", "unknown_tool", task_id, request_id)
            raise PermissionDenied(f"Tool '{tool_name}' is not registered")
        if binding.server == "playwright" and task_id is None:
            self._permissions.record(tool_name, "denied", "task_scope_required", task_id, request_id)
            raise PermissionDenied("Browser tools require an active task scope")
        client: MCPStdioClient | None = None
        client_key = binding.server
        try:
            model = INPUT_MODELS[binding.input_model]
            validated = model.model_validate(arguments)
            path = getattr(validated, "path", None) if binding.server == "filesystem" else None
            policy = self._permissions.authorize(
                tool_name,
                check_approval=False,
                path=path,
                task_id=task_id,
                request_id=request_id,
            )
            server = self._servers.get(binding.server)
            if server is None:
                raise MCPUnavailableError(f"MCP server '{binding.server}' is not configured")
            if policy.requires_approval:
                if approval_id is not None:
                    approval_ok = await self._is_approved(approval_id, tool_name, task_id, request_id)
                elif self._approval_manager is not None and task_id is not None and request_id is not None:
                    approval = self._approval_manager.request(
                        tool_name, task_id, request_id, _approval_summary(tool_name, validated)
                    )
                    if self._task_event_sink is not None:
                        self._task_event_sink(
                            task_id,
                            "approval.requested",
                            approval.model_dump(mode="json"),
                        )
                    try:
                        decision = await self._approval_manager.wait(approval.id)
                    except asyncio.CancelledError:
                        self._approval_manager.cancel_task(task_id)
                        if self._task_event_sink is not None:
                            self._task_event_sink(task_id, "approval.cancelled", {"approval_id": str(approval.id)})
                        raise
                    approval_ok = decision.status == ApprovalStatus.approved
                    if not approval_ok:
                        self._permissions.record(tool_name, "denied", "approval_declined", task_id, request_id)
                        raise PermissionDenied(f"Approval was declined for '{tool_name}'")
                else:
                    approval_ok = False
                self._permissions.authorize(
                    tool_name,
                    approval_verified=approval_ok,
                    path=path,
                    task_id=task_id,
                    request_id=request_id,
                )
            if binding.server == "playwright" and task_id is not None:
                client_key = f"playwright:{task_id}"
            client = self._clients.get(client_key)
            if client is None:
                env = os.environ.copy()
                env.update({key: os.path.expandvars(value) for key, value in server.env.items()})
                client = MCPStdioClient(server.command, server.args, env)
                self._clients[client_key] = client
            result = await client.call_tool(binding.mcp_tool, validated.model_dump(exclude_none=True, by_alias=True))
            if result.get("isError"):
                raise RuntimeError("MCP server reported a tool error")
            self._permissions.record(tool_name, "allowed", "mcp_call_completed", task_id, request_id)
            return result
        except PermissionDenied:
            raise
        except asyncio.CancelledError:
            if client is not None:
                self._clients.pop(client_key, None)
                await asyncio.shield(client.close())
            self._permissions.record(tool_name, "cancelled", "task_cancelled", task_id, request_id)
            raise
        except ValidationError as exc:
            self._permissions.record(tool_name, "rejected", "invalid_arguments", task_id, request_id)
            raise ToolInputError(f"Invalid arguments for '{tool_name}'") from exc
        except Exception as exc:
            if client is not None:
                self._clients.pop(client_key, None)
                await client.close()
            self._permissions.record(tool_name, "failed", type(exc).__name__, task_id, request_id)
            raise ToolExecutionFailure(tool_name, type(exc).__name__) from exc

    def audit_events(self, task_id: UUID | None = None):
        return self._permissions.audit_events(task_id)

    async def close_task(self, task_id: UUID) -> None:
        """Close browser MCP processes owned by one completed or cancelled task."""
        if self._approval_manager is not None:
            self._approval_manager.cancel_task(task_id)
        key = f"playwright:{task_id}"
        client = self._clients.pop(key, None)
        if client is not None:
            await client.close()

    async def close(self) -> None:
        clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            await client.close()

def _approval_summary(tool_name: str, arguments: BaseModel) -> str:
    """Describe the impact without exposing file contents or typed page text."""
    values = arguments.model_dump(exclude_none=True)
    if tool_name == "filesystem.write_file":
        return f"Write or replace the file at {values.get('path', 'the requested path')}? File contents are hidden."
    if tool_name == "github.create_issue":
        repository = "/".join(part for part in (values.get("owner"), values.get("repo")) if part)
        title = values.get("title")
        details = f" titled ‘{title}’" if title else ""
        return f"Create a GitHub issue{details} in {repository or 'the requested repository'}? Issue body is hidden."
    if tool_name.startswith("playwright."):
        if tool_name == "playwright.navigate":
            try:
                target = urlsplit(values.get("url", ""))
                location = f"{target.hostname or 'the requested host'}{target.path or '/'}"
            except ValueError:
                location = "the requested URL"
            return f"Navigate the task's browser to {location}? URL query details are hidden."
        if tool_name == "playwright.close_tab":
            return "Close a browser tab in this task?"
        if tool_name == "playwright.type_text":
            return "Type text into the task's browser page? The text is hidden."
        if tool_name == "playwright.press_key":
            return f"Press a key in the task's browser page ({values.get('key', 'key hidden')})?"
        if tool_name == "playwright.click":
            return "Click an element in the task's browser page?"
        return f"Allow the requested {tool_name.removeprefix('playwright.').replace('_', ' ')} browser action?"
    return f"Allow the requested {tool_name} action to continue for this task?"

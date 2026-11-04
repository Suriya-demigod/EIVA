"""Validate, authorize, execute, and audit configured MCP tool calls."""

import asyncio
import inspect
import os
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError

from backend.core.permission_manager import PermissionDenied, PermissionManager
from backend.mcp.client import MCPStdioClient, MCPUnavailableError
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
    ) -> None:
        self._bindings = bindings
        self._servers = servers
        self._permissions = permissions
        self._approval_checker = approval_checker
        self._clients: dict[str, MCPStdioClient] = {}

    @classmethod
    def from_files(
        cls,
        bindings_path: Path,
        servers_path: Path,
        permissions_path: Path,
        approval_checker: APPROVAL_CHECKER | None = None,
    ) -> "ToolGateway":
        binding_data: Any = yaml.safe_load(bindings_path.read_text(encoding="utf-8")) or {}
        server_data: Any = yaml.safe_load(servers_path.read_text(encoding="utf-8")) or {}
        bindings = {name: ToolBinding.model_validate(item) for name, item in binding_data.get("tools", {}).items()}
        servers = {name: MCPServerSpec.model_validate(item) for name, item in server_data.get("servers", {}).items()}
        for name, binding in bindings.items():
            if binding.input_model not in INPUT_MODELS:
                raise ValueError(f"Tool '{name}' uses unknown input model '{binding.input_model}'")
        return cls(bindings, servers, PermissionManager.from_yaml(permissions_path), approval_checker)

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
            policy = self._permissions.policy_for(tool_name)
            path = getattr(validated, "path", None) if binding.server == "filesystem" else None
            approval_ok = (
                await self._is_approved(approval_id, tool_name, task_id, request_id)
                if policy and policy.requires_approval
                else False
            )
            self._permissions.authorize(
                tool_name,
                approval_verified=approval_ok,
                path=path,
                task_id=task_id,
                request_id=request_id,
            )
            if policy is None:
                raise PermissionDenied(f"Tool '{tool_name}' is disabled or unconfigured")
            server = self._servers.get(binding.server)
            if server is None:
                raise MCPUnavailableError(f"MCP server '{binding.server}' is not configured")
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
        key = f"playwright:{task_id}"
        client = self._clients.pop(key, None)
        if client is not None:
            await client.close()

    async def close(self) -> None:
        clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            await client.close()

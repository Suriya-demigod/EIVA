"""Small MCP stdio JSON-RPC client with lazy server startup."""

import asyncio
import json
from typing import Any

MAX_MCP_MESSAGE_BYTES = 32_000_000


class MCPError(RuntimeError):
    pass


class MCPUnavailableError(MCPError):
    pass


class MCPStdioClient:
    def __init__(self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None, timeout_seconds: float = 30) -> None:
        self._command = command
        self._args = args or []
        self._env = env
        self._timeout_seconds = timeout_seconds
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._next_id = 1
        self._initialized = False

    async def _start(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._command,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=self._env,
                limit=MAX_MCP_MESSAGE_BYTES,
            )
        except (OSError, ValueError) as exc:
            raise MCPUnavailableError(f"Could not start MCP server '{self._command}'") from exc

    async def _exchange(self, message: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise MCPUnavailableError("MCP server process is not connected")
        process.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=self._timeout_seconds)
            if not line:
                raise MCPUnavailableError("MCP server closed its output")
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(response, dict):
                continue
            if response.get("id") == message.get("id"):
                if response.get("error"):
                    error = response["error"]
                    raise MCPError(f"MCP request failed ({error.get('code', 'unknown')})")
                return response.get("result", {})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        return await self._exchange({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

    async def _initialize(self) -> None:
        if self._process is None or self._process.returncode is not None:
            self._initialized = False
        if self._initialized:
            return
        await self._start()
        await self._request(
            "initialize",
            {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "eiva", "version": "0.1.0"}},
        )
        process = self._process
        assert process is not None and process.stdin is not None
        process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode("utf-8"))
        await process.stdin.drain()
        self._initialized = True

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            await self._initialize()
            return await self._request("tools/call", {"name": name, "arguments": arguments})

    async def close(self) -> None:
        process, self._process = self._process, None
        self._initialized = False
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

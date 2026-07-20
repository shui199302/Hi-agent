"""Official MCP SDK adapter for stdio and Streamable HTTP transports."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from .config import Settings, get_settings
from .errors import HiAgentError, ServiceUnavailableError
from .mcp_presets import workspace_mcp_executable
from .models import McpServerConfig
from .schemas import McpToolRead

_SERVER_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_TOOL_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _tool_risk(
    tool: Any,
    *,
    trusted: bool = False,
) -> Literal["read", "network", "write", "execute"]:
    if not trusted:
        # Third-party annotations are untrusted hints. Require approval unless a future built-in
        # registry identifies the exact packaged server implementation.
        return "write"
    annotations = getattr(tool, "annotations", None)
    if annotations is None:
        # MCP annotations are optional hints. An unannotated tool is not safe to auto-run.
        return "write"
    destructive = getattr(annotations, "destructiveHint", False)
    read_only = getattr(annotations, "readOnlyHint", False)
    open_world = getattr(annotations, "openWorldHint", False)
    if destructive:
        return "write"
    if open_world:
        return "network"
    if read_only:
        return "read"
    return "write"


class McpClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def validate_server(self, server: McpServerConfig) -> None:
        if not _SERVER_SLUG.fullmatch(server.name):
            raise HiAgentError(
                "MCP_SERVER_NAME_INVALID",
                "MCP 服务名称必须为小写字母、数字、下划线或连字符组成的 slug",
            )
        if server.transport == "stdio":
            if not server.command:
                raise HiAgentError("MCP_INVALID_CONFIG", "stdio MCP 缺少 command")
            if "\x00" in server.command:
                raise HiAgentError("MCP_INVALID_CONFIG", "MCP command 无效")
            return
        if server.transport != "streamable_http" or not server.url:
            raise HiAgentError("MCP_INVALID_CONFIG", "仅支持 stdio 与 streamable_http")
        parsed = urlparse(server.url)
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        is_local = parsed.hostname in local_hosts
        if not is_local and parsed.scheme != "https":
            raise HiAgentError("MCP_HTTPS_REQUIRED", "远程 MCP 必须使用 HTTPS")
        if not is_local and not (self.settings.allow_remote_mcp and server.allow_remote):
            raise HiAgentError("MCP_REMOTE_DISABLED", "远程 MCP 默认关闭")

    def _stdio_environment(self, server: McpServerConfig) -> dict[str, str]:
        inherited_names = (
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "PYTHONPATH",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
        )
        env = {
            key: value
            for key in inherited_names
            if (value := os.getenv(key)) is not None
        }
        if server.builtin and server.name == "memory":
            env["MEMORY_FILE_PATH"] = str(self.settings.data_dir / "mcp-memory.jsonl")
        if server.builtin and server.name == "sequential-thinking":
            env["DISABLE_THOUGHT_LOGGING"] = "true"
        for target, source in (server.env_refs or {}).items():
            if value := self.settings.resolve_secret(source):
                env[target] = value
        return env

    @asynccontextmanager
    async def _session(self, server: McpServerConfig) -> AsyncIterator[Any]:
        self.validate_server(server)
        try:
            from mcp import ClientSession, StdioServerParameters

            if server.transport == "stdio":
                from mcp.client.stdio import stdio_client

                parameters = StdioServerParameters(
                    command=server.command or "",
                    args=list(server.args),
                    env=self._stdio_environment(server),
                )
                async with (
                    stdio_client(parameters) as streams,
                    ClientSession(streams[0], streams[1]) as session,
                ):
                    await session.initialize()
                    yield session
            else:
                from mcp.client.streamable_http import streamablehttp_client

                async with (
                    streamablehttp_client(server.url or "") as streams,
                    ClientSession(streams[0], streams[1]) as session,
                ):
                    await session.initialize()
                    yield session
        except HiAgentError:
            raise
        except Exception as exc:
            raise ServiceUnavailableError(
                "MCP_UNAVAILABLE",
                f"MCP 服务 {server.name} 不可用",
                server_id=server.id,
                reason=str(exc),
            ) from exc

    async def list_tools(self, server: McpServerConfig) -> list[McpToolRead]:
        for attempt in range(2):
            try:
                async with _timeout(self.settings.tool_timeout_seconds), self._session(server) as session:
                    response = await session.list_tools()
                break
            except HiAgentError as exc:
                if attempt == 1 or exc.code not in {"MCP_TIMEOUT", "MCP_UNAVAILABLE"}:
                    raise
                await asyncio.sleep(0.2)
        trusted = self._is_trusted_builtin(server)
        results: list[McpToolRead] = []
        for tool in response.tools:
            name = str(tool.name)
            qualified = f"mcp.{server.name}.{name}"
            if not _TOOL_COMPONENT.fullmatch(name) or len(qualified) > 64:
                raise HiAgentError(
                    "MCP_TOOL_NAME_INVALID",
                    "MCP 工具名称无法映射为兼容的模型 function name",
                    details={"server_id": server.id, "tool_name": name},
                )
            results.append(
                McpToolRead(
                    name=qualified,
                    description=tool.description or "",
                    input_schema=dict(tool.inputSchema or {"type": "object"}),
                    risk=_tool_risk(tool, trusted=trusted),
                )
            )
        return results

    def _is_trusted_builtin(self, server: McpServerConfig) -> bool:
        if server.transport != "stdio" or not server.command:
            return False
        expected = workspace_mcp_executable(self.settings.project_root).resolve()
        try:
            command = Path(server.command).resolve(strict=True)
        except OSError:
            return False
        return (
            command == expected
            and command.is_file()
            and not Path(server.command).is_symlink()
            and server.args[:2] == ["--transport", "stdio"]
        )

    async def call_tool(self, server: McpServerConfig, qualified_name: str, arguments: dict[str, Any]) -> Any:
        prefix = f"mcp.{server.name}."
        if not qualified_name.startswith(prefix):
            raise HiAgentError("MCP_TOOL_NAME_INVALID", "MCP 工具名称与服务不匹配")
        tool_name = qualified_name[len(prefix) :]
        async with _timeout(self.settings.tool_timeout_seconds), self._session(server) as session:
            response = await session.call_tool(tool_name, arguments)
        if getattr(response, "isError", False):
            raise HiAgentError(
                "MCP_TOOL_FAILED",
                f"MCP 工具 {qualified_name} 执行失败",
                details={"content": _content_to_json(response.content)},
            )
        return _content_to_json(response.content)


def _content_to_json(content: Any) -> list[Any]:
    values: list[Any] = []
    for item in content or []:
        if hasattr(item, "model_dump"):
            values.append(item.model_dump(mode="json"))
        elif hasattr(item, "text"):
            values.append({"type": "text", "text": item.text})
        else:
            values.append(str(item))
    return values


class _timeout:
    """Small wrapper that turns asyncio timeout into a stable service error."""

    def __init__(self, seconds: float) -> None:
        import asyncio

        self._context = asyncio.timeout(seconds)

    async def __aenter__(self) -> None:
        await self._context.__aenter__()

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None:
        try:
            await self._context.__aexit__(exc_type, exc, traceback)
            return None
        except TimeoutError as error:
            raise ServiceUnavailableError("MCP_TIMEOUT", "MCP 请求超时") from error


def get_mcp_client() -> McpClient:
    return McpClient()

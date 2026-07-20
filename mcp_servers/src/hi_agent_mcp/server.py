"""Official-SDK MCP server exposing safe read-only workspace utilities."""

from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .tools import (
    ToolInputError,
    WorkspacePolicy,
    calculate as safe_calculate,
    current_time as get_current_time,
    list_workspace as safe_list_workspace,
    read_text as safe_read_text,
    search_text as safe_search_text,
)

mcp = FastMCP(
    name="Hi-agent Workspace Utilities",
    instructions=(
        "Read-only tools for an explicitly configured workspace plus a safe arithmetic "
        "calculator and timezone clock. Never claim that these tools can modify files."
    ),
    stateless_http=True,
    json_response=True,
)


def _policy() -> WorkspacePolicy:
    root = os.environ.get("HI_AGENT_MCP_WORKSPACE", str(Path.cwd()))
    return WorkspacePolicy.from_root(root)


def _safe_call(function: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return function(*args, **kwargs)
    except ToolInputError as exc:
        return {"ok": False, "error": {"code": "INVALID_TOOL_INPUT", "message": str(exc)}}
    except OSError:
        return {"ok": False, "error": {"code": "WORKSPACE_IO_ERROR", "message": "workspace read failed"}}


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(annotations=READ_ONLY)
def list_workspace(path: str = ".", pattern: str = "*", limit: int = 200) -> dict[str, Any]:
    """Read-only: list regular files under the approved workspace root."""
    return _safe_call(safe_list_workspace, _policy(), path, pattern, limit)


@mcp.tool(annotations=READ_ONLY)
def read_text(path: str, start_line: int = 1, max_lines: int = 200) -> dict[str, Any]:
    """Read-only: return a bounded UTF-8 text range from an approved workspace file."""
    return _safe_call(safe_read_text, _policy(), path, start_line, max_lines)


@mcp.tool(annotations=READ_ONLY)
def search_text(
    query: str,
    path: str = ".",
    pattern: str = "*",
    case_sensitive: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """Read-only: search bounded UTF-8 workspace files for a literal string."""
    return _safe_call(
        safe_search_text,
        _policy(),
        query,
        path,
        pattern,
        case_sensitive,
        max_results,
    )


@mcp.tool(annotations=READ_ONLY)
def calculate(expression: str) -> dict[str, Any]:
    """Read-only: evaluate bounded arithmetic without eval, names, or function calls."""
    return _safe_call(safe_calculate, expression)


@mcp.tool(annotations=READ_ONLY)
def current_time(timezone: str = "UTC") -> dict[str, Any]:
    """Read-only: return the current time for an IANA timezone such as Asia/Shanghai."""
    return _safe_call(get_current_time, timezone)


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("HI_AGENT_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--workspace", default=os.environ.get("HI_AGENT_MCP_WORKSPACE", str(Path.cwd())))
    parser.add_argument("--host", default=os.environ.get("HI_AGENT_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HI_AGENT_MCP_PORT", "8765")))
    args = parser.parse_args()

    try:
        workspace = WorkspacePolicy.from_root(args.workspace).root
    except ToolInputError as exc:
        parser.error(str(exc))
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    allow_remote = os.environ.get("HI_AGENT_MCP_ALLOW_REMOTE_BIND", "false").lower() == "true"
    if args.transport == "streamable-http" and not _is_loopback(args.host) and not allow_remote:
        parser.error("non-loopback HTTP binding requires HI_AGENT_MCP_ALLOW_REMOTE_BIND=true")

    os.environ["HI_AGENT_MCP_WORKSPACE"] = str(workspace)
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

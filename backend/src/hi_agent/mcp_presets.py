"""Curated, disabled-by-default MCP server presets from maintained upstreams."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import McpServerConfig


def workspace_mcp_executable(project_root: Path, *, windows: bool | None = None) -> Path:
    """Return the uv console-script path for the current platform."""

    is_windows = os.name == "nt" if windows is None else windows
    scripts_dir = "Scripts" if is_windows else "bin"
    executable = "hi-agent-mcp.exe" if is_windows else "hi-agent-mcp"
    return project_root / "mcp_servers" / ".venv" / scripts_dir / executable


def builtin_mcp_presets(settings: Settings) -> tuple[dict[str, Any], ...]:
    """Return pinned presets without downloading or starting third-party code."""

    project_root = str(settings.project_root)
    presets: list[dict[str, Any]] = []
    workspace_executable = workspace_mcp_executable(settings.project_root)
    npx_command = "npx.cmd" if os.name == "nt" else "npx"
    uvx_command = "uvx.exe" if os.name == "nt" else "uvx"
    docker_command = "docker.exe" if os.name == "nt" else "docker"
    if (
        workspace_executable.is_file()
        and not workspace_executable.is_symlink()
        and os.access(workspace_executable, os.X_OK)
    ):
        presets.append(
            {
                "name": "workspace",
                "description": "项目内置的只读工作区、文本搜索、计算器和时区工具。",
                "source_url": "https://github.com/modelcontextprotocol/python-sdk",
                "setup_hint": "已随项目安装；路径限制为当前 Hi-agent 项目，敏感文件和符号链接会被拦截。",
                "transport": "stdio",
                "command": str(workspace_executable.resolve()),
                "args": ["--transport", "stdio", "--workspace", project_root],
                "env_refs": {},
                "allow_remote": False,
            }
        )

    presets.extend(
        (
            {
                "name": "filesystem",
                "description": "官方文件系统服务，支持受限目录内的读取、搜索、编辑和移动。",
                "source_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
                "setup_hint": "首次探测会由 npx 下载固定版本；默认只允许访问当前项目，写入工具仍需人工审批。",
                "transport": "stdio",
                "command": npx_command,
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem@2026.7.4",
                    project_root,
                ],
                "env_refs": {},
                "allow_remote": False,
            },
            {
                "name": "git",
                "description": "官方 Git 服务，用于状态、差异、日志、分支和提交等仓库操作。",
                "source_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/git",
                "setup_hint": "首次探测会由 uvx 下载固定版本；仓库路径默认为当前项目，变更类工具需要审批。",
                "transport": "stdio",
                "command": uvx_command,
                "args": [
                    "--from",
                    "mcp-server-git==2026.7.10",
                    "mcp-server-git",
                    "--repository",
                    project_root,
                ],
                "env_refs": {},
                "allow_remote": False,
            },
            {
                "name": "fetch",
                "description": "官方网页抓取服务，将网页正文转换为适合模型阅读的 Markdown。",
                "source_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
                "setup_hint": "首次探测会由 uvx 下载固定版本；该服务可以访问内网地址，启用前请评估 SSRF 风险。",
                "transport": "stdio",
                "command": uvx_command,
                "args": ["--from", "mcp-server-fetch==2026.7.10", "mcp-server-fetch"],
                "env_refs": {},
                "allow_remote": False,
            },
            {
                "name": "time",
                "description": "官方时间服务，查询 IANA 时区时间并执行跨时区换算。",
                "source_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/time",
                "setup_hint": "首次探测会由 uvx 下载固定版本，无需密钥。",
                "transport": "stdio",
                "command": uvx_command,
                "args": ["--from", "mcp-server-time==2026.7.10", "mcp-server-time"],
                "env_refs": {},
                "allow_remote": False,
            },
            {
                "name": "memory",
                "description": "官方知识图谱记忆服务，持久保存实体、关系和观察记录。",
                "source_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
                "setup_hint": "首次探测会由 npx 下载固定版本；记忆写入 data/mcp-memory.jsonl，操作需要审批。",
                "transport": "stdio",
                "command": npx_command,
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-memory@2026.1.26",
                ],
                "env_refs": {},
                "allow_remote": False,
            },
            {
                "name": "sequential-thinking",
                "description": "官方结构化思考服务，支持复杂问题的分步、修订和分支推理。",
                "source_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
                "setup_hint": "首次探测会由 npx 下载固定版本；预置已关闭思考过程的服务端日志。",
                "transport": "stdio",
                "command": npx_command,
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-sequential-thinking@2026.7.4",
                ],
                "env_refs": {},
                "allow_remote": False,
            },
            {
                "name": "github-readonly",
                "description": "GitHub 官方 MCP 服务的只读模式，用于仓库、Issue 和 Pull Request 查询。",
                "source_url": "https://github.com/github/github-mcp-server",
                "setup_hint": "需要运行中的 Docker 和 .env 中的 GITHUB_TOKEN；容器固定为 v1.0.5 并启用只读模式。",
                "transport": "stdio",
                "command": docker_command,
                "args": [
                    "run",
                    "-i",
                    "--rm",
                    "-e",
                    "GITHUB_PERSONAL_ACCESS_TOKEN",
                    "-e",
                    "GITHUB_READ_ONLY=1",
                    "-e",
                    "GITHUB_TOOLSETS=context,repos,issues,pull_requests",
                    "ghcr.io/github/github-mcp-server:v1.0.5",
                ],
                "env_refs": {"GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN"},
                "allow_remote": False,
            },
        )
    )
    return tuple(presets)


def ensure_builtin_mcp_presets(db: Session, settings: Settings, owner_id: str) -> None:
    """Install missing presets for the bootstrap administrator without replacing custom rows."""

    existing_names = set(
        db.scalars(select(McpServerConfig.name).where(McpServerConfig.owner_id == owner_id)).all()
    )
    for preset in builtin_mcp_presets(settings):
        if preset["name"] in existing_names:
            continue
        db.add(
            McpServerConfig(
                owner_id=owner_id,
                builtin=True,
                enabled=False,
                **preset,
            )
        )

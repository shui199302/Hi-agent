from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_discovery_annotations_and_call(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("Hi-agent protocol test\n", encoding="utf-8")

    async def exercise() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "hi_agent_mcp.server",
                "--transport",
                "stdio",
                "--workspace",
                str(tmp_path),
            ],
            env={key: value for key in ("PATH", "PYTHONPATH", "LANG") if (value := os.getenv(key))},
        )
        async with asyncio.timeout(15), stdio_client(parameters) as streams, ClientSession(
            streams[0], streams[1]
        ) as session:
            await session.initialize()
            discovered = await session.list_tools()
            assert {tool.name for tool in discovered.tools} == {
                "calculate",
                "current_time",
                "list_workspace",
                "read_text",
                "search_text",
            }
            assert all(tool.annotations and tool.annotations.readOnlyHint for tool in discovered.tools)
            response = await session.call_tool("calculate", {"expression": "(2 + 3) * 4"})
            assert not response.isError
            assert response.structuredContent == {"expression": "(2 + 3) * 4", "result": 20}

    asyncio.run(exercise())

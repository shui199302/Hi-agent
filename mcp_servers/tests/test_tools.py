from __future__ import annotations

from pathlib import Path

import pytest

from hi_agent_mcp.tools import ToolInputError, WorkspacePolicy, calculate, read_text, search_text


def test_workspace_reads_and_searches_text(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("alpha\nbeta alpha\n", encoding="utf-8")
    policy = WorkspacePolicy.from_root(tmp_path)
    assert read_text(policy, "notes.md", 2, 1)["text"] == "beta alpha"
    result = search_text(policy, "ALPHA", pattern="*.md")
    assert [item["line"] for item in result["matches"]] == [1, 2]


def test_workspace_blocks_escape_and_secrets(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    policy = WorkspacePolicy.from_root(tmp_path)
    with pytest.raises(ToolInputError):
        read_text(policy, ".env")
    with pytest.raises(ToolInputError):
        policy.resolve("../outside")


def test_calculator_allows_arithmetic_and_rejects_code() -> None:
    assert calculate("(2 + 3) * 4")["result"] == 20
    with pytest.raises(ToolInputError):
        calculate("__import__('os').system('id')")

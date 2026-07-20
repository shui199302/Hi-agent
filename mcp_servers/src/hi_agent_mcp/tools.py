"""Dependency-free, testable implementations for the example MCP tools."""

from __future__ import annotations

import ast
import fnmatch
import math
import operator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_READ_BYTES = 1024 * 1024
MAX_SEARCH_BYTES = 1024 * 1024
MAX_LIST_LIMIT = 500
MAX_SEARCH_LIMIT = 200
BLOCKED_PARTS = {
    ".git",
    ".hg",
    ".ssh",
    ".svn",
    "node_modules",
    "__pycache__",
}
BLOCKED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
    "credentials",
    "credentials.json",
    "secrets.json",
}
BLOCKED_SUFFIXES = {".key", ".p12", ".pfx", ".pem"}
TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}


class ToolInputError(ValueError):
    """A safe, user-correctable MCP tool input error."""


@dataclass(frozen=True)
class WorkspacePolicy:
    """Resolve and inspect files below one approved workspace root."""

    root: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "WorkspacePolicy":
        resolved = Path(root).expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise ToolInputError("workspace root must be a directory")
        return cls(resolved)

    def resolve(self, value: str = ".", *, require_file: bool = False) -> Path:
        if not value or "\x00" in value:
            raise ToolInputError("path must be a non-empty string")
        supplied = Path(value).expanduser()
        unresolved = supplied if supplied.is_absolute() else self.root / supplied
        try:
            resolved = unresolved.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ToolInputError("path does not exist or cannot be resolved") from exc
        if resolved != self.root and self.root not in resolved.parents:
            raise ToolInputError("path escapes the workspace root")
        relative = resolved.relative_to(self.root)
        self._check_sensitive(relative)
        if unresolved.is_symlink():
            raise ToolInputError("direct symbolic links are not readable")
        if require_file and not resolved.is_file():
            raise ToolInputError("path must be a regular file")
        return resolved

    def _check_sensitive(self, relative: Path) -> None:
        lowered_parts = {part.lower() for part in relative.parts}
        name = relative.name.lower()
        if lowered_parts & BLOCKED_PARTS:
            raise ToolInputError("path is in a blocked workspace directory")
        if name in BLOCKED_NAMES or name.startswith(".env."):
            raise ToolInputError("secret-bearing configuration files are blocked")
        if relative.suffix.lower() in BLOCKED_SUFFIXES:
            raise ToolInputError("private key and certificate files are blocked")

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix() or "."

    def iter_files(self, start: str, pattern: str) -> list[Path]:
        base = self.resolve(start)
        if not base.is_dir():
            raise ToolInputError("search path must be a directory")
        validate_pattern(pattern)
        found: list[Path] = []
        for candidate in base.rglob("*"):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                resolved = candidate.resolve(strict=True)
                if resolved != self.root and self.root not in resolved.parents:
                    continue
                relative = resolved.relative_to(self.root)
                self._check_sensitive(relative)
            except (OSError, RuntimeError, ToolInputError, ValueError):
                continue
            relative_to_base = resolved.relative_to(base).as_posix()
            if fnmatch.fnmatch(relative_to_base, pattern) or fnmatch.fnmatch(resolved.name, pattern):
                found.append(resolved)
        return sorted(set(found), key=lambda path: self.relative(path))


def validate_pattern(pattern: str) -> None:
    if not pattern or len(pattern) > 256 or "\x00" in pattern:
        raise ToolInputError("glob pattern must contain 1 to 256 characters")
    pure = PurePosixPath(pattern.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts:
        raise ToolInputError("glob pattern cannot be absolute or contain '..'")


def list_workspace(policy: WorkspacePolicy, path: str = ".", pattern: str = "*", limit: int = 200) -> dict[str, Any]:
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise ToolInputError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
    files = policy.iter_files(path, pattern)
    selected = files[:limit]
    return {
        "workspace": policy.root.name,
        "path": policy.relative(policy.resolve(path)),
        "pattern": pattern,
        "truncated": len(files) > limit,
        "files": [
            {"path": policy.relative(item), "size": item.stat().st_size}
            for item in selected
        ],
    }


def _read_utf8(path: Path, max_bytes: int) -> str:
    if path.stat().st_size > max_bytes:
        raise ToolInputError(f"file exceeds the {max_bytes}-byte read limit")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        raise ToolInputError("binary files are not readable")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ToolInputError("file is not valid UTF-8 text") from exc


def read_text(policy: WorkspacePolicy, path: str, start_line: int = 1, max_lines: int = 200) -> dict[str, Any]:
    if start_line < 1:
        raise ToolInputError("start_line must be at least 1")
    if not 1 <= max_lines <= 1_000:
        raise ToolInputError("max_lines must be between 1 and 1000")
    file_path = policy.resolve(path, require_file=True)
    lines = _read_utf8(file_path, MAX_READ_BYTES).splitlines()
    start = min(start_line - 1, len(lines))
    selected = lines[start : start + max_lines]
    return {
        "path": policy.relative(file_path),
        "start_line": start + 1 if selected else start_line,
        "end_line": start + len(selected),
        "total_lines": len(lines),
        "truncated": start + len(selected) < len(lines),
        "text": "\n".join(selected),
    }


def search_text(
    policy: WorkspacePolicy,
    query: str,
    path: str = ".",
    pattern: str = "*",
    case_sensitive: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    if not query or len(query) > 500 or "\x00" in query:
        raise ToolInputError("query must contain 1 to 500 characters")
    if not 1 <= max_results <= MAX_SEARCH_LIMIT:
        raise ToolInputError(f"max_results must be between 1 and {MAX_SEARCH_LIMIT}")
    needle = query if case_sensitive else query.casefold()
    matches: list[dict[str, Any]] = []
    files_scanned = 0
    for file_path in policy.iter_files(path, pattern):
        if file_path.suffix.lower() not in TEXT_SUFFIXES or file_path.stat().st_size > MAX_SEARCH_BYTES:
            continue
        try:
            lines = _read_utf8(file_path, MAX_SEARCH_BYTES).splitlines()
        except ToolInputError:
            continue
        files_scanned += 1
        for line_number, line in enumerate(lines, 1):
            haystack = line if case_sensitive else line.casefold()
            if needle in haystack:
                matches.append(
                    {
                        "path": policy.relative(file_path),
                        "line": line_number,
                        "text": line[:500],
                    }
                )
                if len(matches) >= max_results:
                    return {"query": query, "files_scanned": files_scanned, "truncated": True, "matches": matches}
    return {"query": query, "files_scanned": files_scanned, "truncated": False, "matches": matches}


BINARY_OPERATORS: dict[type[ast.operator], Callable[[int | float, int | float], int | float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[int | float], int | float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _bounded_number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolInputError("only numeric literals are allowed")
    if not math.isfinite(float(value)) or abs(value) > 1e100:
        raise ToolInputError("numeric value is outside the supported range")
    return value


def _calculate_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant):
        return _bounded_number(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return _bounded_number(UNARY_OPERATORS[type(node.op)](_calculate_node(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
        left = _calculate_node(node.left)
        right = _calculate_node(node.right)
        if isinstance(node.op, ast.Pow) and (abs(left) > 1e10 or abs(right) > 10):
            raise ToolInputError("exponentiation is outside the supported range")
        try:
            result = BINARY_OPERATORS[type(node.op)](left, right)
        except (ArithmeticError, OverflowError) as exc:
            raise ToolInputError("calculation is undefined or outside the supported range") from exc
        return _bounded_number(result)
    raise ToolInputError("expression may contain only numbers, parentheses, and arithmetic operators")


def calculate(expression: str) -> dict[str, int | float | str]:
    if not expression or len(expression) > 256 or "\x00" in expression:
        raise ToolInputError("expression must contain 1 to 256 characters")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolInputError("expression is not valid arithmetic") from exc
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ToolInputError("expression is too complex")
    result = _calculate_node(tree.body)
    return {"expression": expression, "result": result}


def current_time(timezone: str = "UTC") -> dict[str, str]:
    if not timezone or len(timezone) > 64 or "\x00" in timezone:
        raise ToolInputError("timezone must contain 1 to 64 characters")
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ToolInputError("unknown IANA timezone") from exc
    now = datetime.now(zone)
    return {"timezone": timezone, "iso8601": now.isoformat(timespec="seconds")}

"""Agent Skills discovery with progressive disclosure and path confinement."""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass
from pathlib import Path

from .config import Settings, get_settings
from .errors import HiAgentError, NotFoundError
from .schemas import SkillDetail, SkillMetadata

_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_RESOURCE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class _ParsedSkill:
    metadata: dict[str, str]
    body: str


def _parse_skill_md(text: str) -> _ParsedSkill:
    if not text.startswith("---"):
        raise ValueError("SKILL.md 缺少 YAML frontmatter")
    lines = text.splitlines()
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter 未闭合") from exc
    metadata: dict[str, str] = {}
    for raw in lines[1:closing]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    return _ParsedSkill(metadata=metadata, body="\n".join(lines[closing + 1 :]).strip())


class SkillRegistry:
    """Reads only metadata during listing and instructions on explicit load."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.skills_dir.resolve()

    def _confined_directory(self, name: str) -> Path:
        if not _SKILL_NAME.fullmatch(name):
            raise HiAgentError("INVALID_SKILL_NAME", "Skill 名称必须使用 kebab-case")
        lexical = self.root / name
        candidate = lexical.resolve()
        if not candidate.is_relative_to(self.root) or lexical.is_symlink():
            raise HiAgentError("SKILL_PATH_ESCAPE", "Skill 路径越界")
        if not candidate.is_dir():
            raise NotFoundError("Skill", name)
        return candidate

    def list(self) -> list[SkillMetadata]:
        if not self.root.exists():
            return []
        results: list[SkillMetadata] = []
        for directory in sorted(self.root.iterdir(), key=lambda item: item.name):
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                results.append(self._metadata(directory))
            except (OSError, ValueError) as exc:
                results.append(
                    SkillMetadata(
                        name=directory.name,
                        description="",
                        directory=directory.name,
                        has_scripts=(directory / "scripts").is_dir(),
                        scripts_allowed=False,
                        valid=False,
                        error=str(exc),
                    )
                )
        return results

    def _metadata(self, directory: Path) -> SkillMetadata:
        parsed = _parse_skill_md((directory / "SKILL.md").read_text(encoding="utf-8"))
        name = parsed.metadata.get("name", directory.name)
        description = parsed.metadata.get("description", "")
        if name != directory.name or not _SKILL_NAME.fullmatch(name):
            raise ValueError("frontmatter name 必须与目录名一致并使用 kebab-case")
        if not description or len(description) > 1024:
            raise ValueError("frontmatter description 必须为 1-1024 个字符")
        scripts_dir = directory / "scripts"
        has_scripts = scripts_dir.is_dir() and any(path.is_file() for path in scripts_dir.iterdir())
        return SkillMetadata(
            name=name,
            description=description,
            directory=directory.name,
            has_scripts=has_scripts,
            scripts_allowed=has_scripts and self.settings.allow_skill_scripts,
            valid=True,
        )

    def get(self, name: str) -> SkillDetail:
        directory = self._confined_directory(name)
        metadata = self._metadata(directory)
        parsed = _parse_skill_md((directory / "SKILL.md").read_text(encoding="utf-8"))
        return SkillDetail(
            **metadata.model_dump(),
            instructions=parsed.body,
            references=self._safe_children(directory, "references"),
            assets=self._safe_children(directory, "assets"),
        )

    def read_resource(self, name: str, relative_path: str) -> dict[str, str | int]:
        """Read one bounded UTF-8 reference/asset after the model has loaded the Skill."""

        directory = self._confined_directory(name)
        if not relative_path or "\x00" in relative_path:
            raise HiAgentError("SKILL_RESOURCE_INVALID", "Skill 资源路径无效")
        supplied = Path(relative_path)
        if supplied.is_absolute() or ".." in supplied.parts or supplied.parts[0] not in {
            "references",
            "assets",
        }:
            raise HiAgentError(
                "SKILL_RESOURCE_INVALID",
                "只允许读取 Skill 的 references 或 assets",
            )
        lexical = directory / supplied
        try:
            resource = lexical.resolve(strict=True)
        except OSError as exc:
            raise NotFoundError("SkillResource", relative_path) from exc
        allowed_root = (directory / supplied.parts[0]).resolve()
        if (
            lexical.is_symlink()
            or not resource.is_relative_to(allowed_root)
            or not resource.is_file()
        ):
            raise HiAgentError("SKILL_RESOURCE_PATH_ESCAPE", "Skill 资源路径越界")
        size = resource.stat().st_size
        if size > _MAX_RESOURCE_BYTES:
            raise HiAgentError(
                "SKILL_RESOURCE_TOO_LARGE",
                "Skill 资源超过 1MB 读取限制",
                details={"max_bytes": _MAX_RESOURCE_BYTES},
            )
        data = resource.read_bytes()
        if b"\x00" in data[:8192]:
            raise HiAgentError("SKILL_RESOURCE_BINARY", "Skill 二进制资源不可直接读取")
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HiAgentError("SKILL_RESOURCE_ENCODING", "Skill 资源不是 UTF-8 文本") from exc
        return {"path": supplied.as_posix(), "content": content, "size_bytes": size}

    @staticmethod
    def _safe_children(directory: Path, child: str) -> builtins.list[str]:
        root = (directory / child).resolve()
        if not root.is_dir() or not root.is_relative_to(directory.resolve()):
            return []
        return sorted(
            str(path.relative_to(directory))
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)
        )

    def enabled_prompt(self, names: builtins.list[str]) -> str:
        summaries: builtins.list[str] = []
        available = {item.name: item for item in self.list() if item.valid}
        for name in names:
            if item := available.get(name):
                summaries.append(f"- {item.name}: {item.description}")
        if not summaries:
            return ""
        return "\n\n可用 Skills（需要时调用对应 skill.*.load 工具读取完整指令）：\n" + "\n".join(summaries)


def get_skill_registry() -> SkillRegistry:
    return SkillRegistry()

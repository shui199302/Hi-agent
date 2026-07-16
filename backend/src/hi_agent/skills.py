"""Agent Skills discovery with progressive disclosure and path confinement."""

from __future__ import annotations

import builtins
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from .config import Settings, get_settings
from .errors import HiAgentError, NotFoundError
from .schemas import RemoteSkillRead, SkillCreateRequest, SkillDetail, SkillMetadata

_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_RESOURCE_BYTES = 1024 * 1024
_MAX_REMOTE_FILES = 64
_MAX_REMOTE_BYTES = 2 * 1024 * 1024
_ALLOWED_REMOTE_ROOTS = {"SKILL.md", "agents", "references", "assets", "scripts"}
_DANGEROUS_REMOTE = re.compile(
    r"(?i)(curl\s|wget\s|rm\s+-rf|eval\s*\(|exec\s*\(|subprocess|os\.system|"
    r"ignore\s+(all|previous)\s+instructions|BEGIN\s+(RSA|OPENSSH)\s+PRIVATE\s+KEY)"
)


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
        if (
            supplied.is_absolute()
            or ".." in supplied.parts
            or supplied.parts[0]
            not in {
                "references",
                "assets",
            }
        ):
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
        if lexical.is_symlink() or not resource.is_relative_to(allowed_root) or not resource.is_file():
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

    def _github_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Hi-agent/0.1"}
        if token := os.getenv("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _catalog(value: str) -> tuple[str, str, str]:
        repository, separator, ref = value.partition("@")
        if not separator:
            ref = "main"
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise HiAgentError("SKILL_CATALOG_INVALID", "远程 Skill 目录格式无效")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", ref):
            raise HiAgentError("SKILL_CATALOG_INVALID", "远程 Skill revision 无效")
        owner, repo = repository.split("/", 1)
        return owner, repo, ref

    def _approved_catalog(self, value: str) -> tuple[str, str, str]:
        if value not in self.settings.remote_skill_catalog_list:
            raise HiAgentError("SKILL_CATALOG_NOT_APPROVED", "远程 Skill 来源不在允许列表")
        return self._catalog(value)

    def search_remote(self, query: str) -> builtins.list[RemoteSkillRead]:
        if not self.settings.allow_remote_skills:
            raise HiAgentError("REMOTE_SKILLS_DISABLED", "远程 Skill 搜索未启用")
        terms = [term for term in re.findall(r"[a-z0-9\u3400-\u9fff]+", query.lower()) if len(term) > 1]
        results: builtins.list[RemoteSkillRead] = []
        with httpx.Client(timeout=15, follow_redirects=False, headers=self._github_headers()) as client:
            for catalog in self.settings.remote_skill_catalog_list:
                owner, repo, ref = self._approved_catalog(catalog)
                response = client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/git/trees/{quote(ref, safe='')}",
                    params={"recursive": "1"},
                )
                if response.status_code != 200:
                    continue
                tree = response.json().get("tree", [])
                paths = [str(item.get("path", "")) for item in tree if str(item.get("path", "")).endswith("/SKILL.md")]
                ranked = sorted(paths, key=lambda path: (not any(term in path.lower() for term in terms), len(path)))
                for path in ranked[:20]:
                    raw = client.get(
                        f"https://raw.githubusercontent.com/{owner}/{repo}/{quote(ref, safe='')}/{quote(path)}"
                    )
                    if raw.status_code != 200 or len(raw.content) > _MAX_RESOURCE_BYTES:
                        continue
                    try:
                        parsed = _parse_skill_md(raw.text)
                        name = parsed.metadata.get("name", Path(path).parent.name)
                        description = parsed.metadata.get("description", "")
                    except ValueError:
                        continue
                    haystack = f"{name} {description}".lower()
                    if terms and not any(term in haystack for term in terms):
                        continue
                    prefix = f"{Path(path).parent.as_posix()}/"
                    results.append(
                        RemoteSkillRead(
                            catalog=catalog,
                            repository=f"{owner}/{repo}",
                            ref=ref,
                            path=Path(path).parent.as_posix(),
                            name=name,
                            description=description,
                            source_url=f"https://github.com/{owner}/{repo}/tree/{ref}/{Path(path).parent.as_posix()}",
                            has_scripts=any(str(item.get("path", "")).startswith(prefix + "scripts/") for item in tree),
                        )
                    )
                    if len(results) >= 30:
                        return results
        return results

    def install_remote(self, catalog: str, skill_path: str, *, confirm: bool, replace: bool) -> SkillMetadata:
        if not confirm:
            raise HiAgentError("SKILL_INSTALL_APPROVAL_REQUIRED", "安装远程 Skill 需要明确确认", status_code=409)
        owner, repo, ref = self._approved_catalog(catalog)
        supplied = Path(skill_path)
        if supplied.is_absolute() or ".." in supplied.parts or not supplied.parts:
            raise HiAgentError("SKILL_REMOTE_PATH_INVALID", "远程 Skill 路径无效")
        with httpx.Client(timeout=20, follow_redirects=False, headers=self._github_headers()) as client:
            tree_response = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{quote(ref, safe='')}",
                params={"recursive": "1"},
            )
            if tree_response.status_code != 200:
                raise HiAgentError("SKILL_REMOTE_UNAVAILABLE", "无法读取远程 Skill 目录", status_code=503)
            prefix = supplied.as_posix().rstrip("/") + "/"
            paths = [
                str(item.get("path", ""))
                for item in tree_response.json().get("tree", [])
                if item.get("type") == "blob" and str(item.get("path", "")).startswith(prefix)
            ]
            if not paths or f"{prefix}SKILL.md" not in paths or len(paths) > _MAX_REMOTE_FILES:
                raise HiAgentError("SKILL_REMOTE_PACKAGE_INVALID", "远程 Skill 文件缺失或数量超限")
            payloads: dict[str, bytes] = {}
            total = 0
            for remote_path in paths:
                relative = Path(remote_path).relative_to(supplied)
                if relative.parts[0] not in _ALLOWED_REMOTE_ROOTS or ".." in relative.parts:
                    raise HiAgentError("SKILL_REMOTE_PACKAGE_INVALID", "远程 Skill 包含越界文件")
                response = client.get(
                    f"https://raw.githubusercontent.com/{owner}/{repo}/{quote(ref, safe='')}/{quote(remote_path)}"
                )
                if response.status_code != 200:
                    raise HiAgentError("SKILL_REMOTE_UNAVAILABLE", "远程 Skill 文件下载失败", status_code=503)
                total += len(response.content)
                if total > _MAX_REMOTE_BYTES or b"\x00" in response.content[:8192]:
                    raise HiAgentError("SKILL_REMOTE_PACKAGE_INVALID", "远程 Skill 过大或包含二进制文件")
                if _DANGEROUS_REMOTE.search(response.text):
                    raise HiAgentError("SKILL_REMOTE_SECURITY_REJECTED", f"安全扫描拒绝文件：{relative.as_posix()}")
                payloads[relative.as_posix()] = response.content
        parsed = _parse_skill_md(payloads["SKILL.md"].decode("utf-8"))
        name = parsed.metadata.get("name", "")
        if not _SKILL_NAME.fullmatch(name) or name != supplied.name:
            raise HiAgentError("SKILL_REMOTE_PACKAGE_INVALID", "远程 Skill 名称与目录不一致")
        destination = self.root / name
        if destination.exists() and not replace:
            raise HiAgentError("SKILL_ALREADY_EXISTS", "同名 Skill 已存在", status_code=409)
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hi-agent-skill-") as temporary:
            staged = Path(temporary) / name
            for relative_name, content in payloads.items():
                target = staged / relative_name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self._metadata(staged)
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(staged, destination)
        return self._metadata(destination)

    def create_skill(self, payload: SkillCreateRequest) -> SkillMetadata:
        if not payload.confirm:
            raise HiAgentError("SKILL_CREATE_APPROVAL_REQUIRED", "创建 Skill 需要明确确认", status_code=409)
        destination = self.root / payload.name
        if destination.exists():
            raise HiAgentError("SKILL_ALREADY_EXISTS", "同名 Skill 已存在", status_code=409)
        destination.mkdir(parents=True)
        (destination / "SKILL.md").write_text(
            f"---\nname: {payload.name}\ndescription: {json.dumps(payload.description, ensure_ascii=False)}\n"
            f"---\n\n{payload.instructions.strip()}\n",
            encoding="utf-8",
        )
        agents = destination / "agents"
        agents.mkdir()
        (agents / "openai.yaml").write_text(
            "interface:\n"
            f"  display_name: {json.dumps(payload.display_name, ensure_ascii=False)}\n"
            f"  short_description: {json.dumps(payload.short_description, ensure_ascii=False)}\n"
            f"  default_prompt: {json.dumps(payload.default_prompt, ensure_ascii=False)}\n",
            encoding="utf-8",
        )
        return self._metadata(destination)


def get_skill_registry() -> SkillRegistry:
    return SkillRegistry()

"""Application configuration with safe local-first defaults."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    # backend/src/hi_agent/config.py -> project root
    return Path(__file__).resolve().parents[3]


_SECRET_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,119}$")


class Settings(BaseSettings):
    """Settings loaded from `HI_AGENT_*` variables and the project `.env` file."""

    model_config = SettingsConfigDict(
        env_prefix="HI_AGENT_",
        env_file=(_project_root() / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Hi-agent"
    host: str = "127.0.0.1"
    port: int = 8787
    debug: bool = False
    data_dir: Path = Field(default_factory=lambda: _project_root() / "data")
    dotenv_path: Path = Field(default_factory=lambda: _project_root() / ".env")
    web_dist_dir: Path = Field(default_factory=lambda: _project_root() / "web" / "dist")
    skills_dir: Path = Field(default_factory=lambda: _project_root() / "skills")
    database_url: str | None = None
    upload_max_bytes: int = 50 * 1024 * 1024
    artifact_max_bytes: int = 25 * 1024 * 1024
    artifact_max_slides: int = 30
    ocr_max_pages: int = 100
    ocr_render_dpi: int = 180
    ocr_timeout_seconds: float = 120.0
    embedding_backend: Literal["fastembed", "deterministic"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    qdrant_path: Path | None = None
    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_model: str = ""
    llm_api_key_env: str = "HI_AGENT_LLM_API_KEY"
    run_timeout_seconds: float = 180.0
    tool_timeout_seconds: float = 30.0
    event_poll_seconds: float = 0.25
    sse_heartbeat_seconds: float = 15.0
    allow_remote_mcp: bool = False
    allow_skill_scripts: bool = False
    allow_remote_skills: bool = True
    remote_skill_catalogs: str = "vercel-labs/skills@main,openai/skills@main"
    clawhub_registry_url: str = "https://clawhub.ai"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    auth_mode: Literal["development", "production"] = "development"
    auth_session_days: int = Field(default=14, ge=1, le=90)
    auth_cookie_secure: bool = False
    auth_bootstrap_username: str = "初始化管理员"
    auth_otp_ttl_seconds: int = Field(default=300, ge=60, le=900)
    auth_otp_resend_seconds: int = Field(default=60, ge=30, le=300)
    auth_otp_max_attempts: int = Field(default=5, ge=3, le=10)

    @field_validator("host")
    @classmethod
    def only_loopback_by_default(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("HI_AGENT_HOST must be a loopback address")
        return value

    @model_validator(mode="after")
    def anchor_relative_paths(self) -> Settings:
        """Make path settings independent from the process working directory."""

        for field_name in (
            "data_dir",
            "web_dist_dir",
            "skills_dir",
            "dotenv_path",
        ):
            value = getattr(self, field_name).expanduser()
            if not value.is_absolute():
                value = _project_root() / value
            setattr(self, field_name, value.resolve())
        if self.qdrant_path is not None:
            value = self.qdrant_path.expanduser()
            if not value.is_absolute():
                value = _project_root() / value
            self.qdrant_path = value.resolve()
        if self.auth_mode == "production" and not self.auth_cookie_secure:
            raise ValueError("HI_AGENT_AUTH_COOKIE_SECURE must be true in production mode")
        return self

    @property
    def remote_skill_catalog_list(self) -> list[str]:
        return [item.strip() for item in self.remote_skill_catalogs.split(",") if item.strip()]

    @property
    def project_root(self) -> Path:
        return _project_root()

    @property
    def sqlite_url(self) -> str:
        if not self.database_url:
            return f"sqlite:///{self.data_dir / 'hi-agent.sqlite3'}"
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix) and not self.database_url.startswith("sqlite:////"):
            path_text = self.database_url[len(prefix) :]
            if path_text != ":memory:":
                path = Path(path_text).expanduser()
                if not path.is_absolute():
                    path = _project_root() / path
                return f"sqlite:///{path.resolve()}"
        return self.database_url

    @property
    def vectors_dir(self) -> Path:
        return self.qdrant_path or self.data_dir / "qdrant"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def checkpoints_path(self) -> Path:
        return self.data_dir / "langgraph-checkpoints.sqlite3"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.vectors_dir, self.uploads_dir, self.artifacts_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def mock_auth_enabled(self) -> bool:
        return self.auth_mode == "development"

    def resolve_secret(self, env_name: str) -> str:
        """Resolve a secret without adding it to settings dumps, logs, or persistence.

        Process environment values take precedence. The dotenv file is parsed on demand so model
        endpoints can safely reference arbitrary validated environment-variable names.
        """

        if not _SECRET_ENV_NAME.fullmatch(env_name):
            return ""
        if value := os.getenv(env_name):
            return value
        try:
            if not self.dotenv_path.is_file():
                return ""
            value = dotenv_values(
                self.dotenv_path,
                encoding="utf-8",
                interpolate=False,
            ).get(env_name)
        except OSError:
            return ""
        return value or ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test helper for applying environment changes."""

    get_settings.cache_clear()

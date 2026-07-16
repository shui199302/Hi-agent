"""Public API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class ModelEndpointBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: AnyHttpUrl
    model: str = Field(min_length=1, max_length=250)
    api_key_env: str = Field(default="HI_AGENT_LLM_API_KEY", pattern=r"^[A-Z][A-Z0-9_]{1,119}$")
    timeout_seconds: float = Field(default=120.0, ge=1, le=600)
    enabled: bool = True
    mock: bool = False


class ModelEndpointCreate(ModelEndpointBase):
    pass


class ModelEndpointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: AnyHttpUrl | None = None
    model: str | None = Field(default=None, min_length=1, max_length=250)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,119}$")
    timeout_seconds: float | None = Field(default=None, ge=1, le=600)
    enabled: bool | None = None
    mock: bool | None = None


class ModelEndpointRead(ApiModel):
    id: str
    name: str
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float
    enabled: bool
    mock: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", min_length=1, max_length=250)
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    top_k: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def overlap_is_smaller(self) -> KnowledgeBaseBase:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=50)


class KnowledgeBaseReindex(BaseModel):
    embedding_model: str = Field(min_length=1, max_length=250)
    chunk_size: int = Field(ge=100, le=4000)
    chunk_overlap: int = Field(ge=0, le=1000)
    top_k: int = Field(ge=1, le=50)

    @model_validator(mode="after")
    def overlap_is_smaller(self) -> KnowledgeBaseReindex:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class KnowledgeBaseRead(ApiModel):
    id: str
    name: str
    description: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentRead(ApiModel):
    id: str
    knowledge_base_id: str
    filename: str
    media_type: str
    sha256: str
    size_bytes: int
    status: str
    error: str | None
    chunk_count: int
    created_at: datetime


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    mode: Literal["dense", "lexical", "hybrid"] = "hybrid"


class SearchHit(BaseModel):
    document_id: str
    filename: str
    page: int | None
    chunk_index: int
    content: str
    score: float
    dense_score: float | None = None
    lexical_score: float | None = None
    channels: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    items: list[SearchHit]
    mode: str = "hybrid"
    query: str = ""


class McpServerBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    transport: Literal["stdio", "streamable_http"]
    command: str | None = Field(default=None, max_length=500)
    args: list[str] = Field(default_factory=list, max_length=100)
    url: AnyHttpUrl | None = None
    env_refs: dict[str, str] = Field(default_factory=dict)
    enabled: bool = False
    allow_remote: bool = False

    @field_validator("env_refs")
    @classmethod
    def env_refs_only(cls, value: dict[str, str]) -> dict[str, str]:
        for target, source in value.items():
            if not target.isidentifier() or not source.replace("_", "A").isalnum() or source.upper() != source:
                raise ValueError("env_refs maps environment names to uppercase environment-variable names")
        return value

    @model_validator(mode="after")
    def transport_fields(self) -> McpServerBase:
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio transport requires command")
        if self.transport == "streamable_http" and self.url is None:
            raise ValueError("streamable_http transport requires url")
        return self


class McpServerCreate(McpServerBase):
    pass


class McpServerUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    command: str | None = Field(default=None, max_length=500)
    args: list[str] | None = Field(default=None, max_length=100)
    url: AnyHttpUrl | None = None
    env_refs: dict[str, str] | None = None
    enabled: bool | None = None
    allow_remote: bool | None = None


class McpServerRead(ApiModel):
    id: str
    name: str
    transport: str
    command: str | None
    args: list[str]
    url: str | None
    env_refs: dict[str, str]
    enabled: bool
    allow_remote: bool
    status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class McpToolRead(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    risk: Literal["read", "network", "write", "execute"] = "read"


class McpProbeResponse(BaseModel):
    status: str
    tools: list[McpToolRead] = Field(default_factory=list)
    error: str | None = None


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    system_prompt: str = Field(default="你是一个可靠的中文智能体助手。", min_length=1, max_length=100_000)
    model_endpoint_id: str | None = None
    knowledge_base_id: str | None = None
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
    max_tool_loops: int = Field(default=12, ge=1, le=12)
    enabled: bool = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=100_000)
    model_endpoint_id: str | None = None
    knowledge_base_id: str | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None
    tool_policy: dict[str, Any] | None = None
    max_tool_loops: int | None = Field(default=None, ge=1, le=12)
    enabled: bool | None = None


class AgentRead(ApiModel):
    id: str
    name: str
    description: str
    system_prompt: str
    model_endpoint_id: str | None
    knowledge_base_id: str | None
    skills: list[str]
    mcp_servers: list[str]
    tool_policy: dict[str, Any]
    max_tool_loops: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AgentRevisionRead(ApiModel):
    id: str
    agent_id: str
    version: int
    snapshot: dict[str, Any]
    reason: str
    created_at: datetime


class SkillMetadata(BaseModel):
    name: str
    description: str
    directory: str
    has_scripts: bool
    scripts_allowed: bool
    valid: bool
    error: str | None = None


class SkillDetail(SkillMetadata):
    instructions: str
    references: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)


class RemoteSkillRead(BaseModel):
    catalog: str
    repository: str
    ref: str
    path: str
    name: str
    description: str
    source_url: str
    has_scripts: bool = False
    license: str | None = None


class RemoteSkillInstall(BaseModel):
    catalog: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=500)
    confirm: bool
    replace: bool = False


class SkillCreateRequest(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=63)
    description: str = Field(min_length=20, max_length=1024)
    instructions: str = Field(min_length=20, max_length=20_000)
    display_name: str = Field(min_length=1, max_length=80)
    short_description: str = Field(min_length=1, max_length=160)
    default_prompt: str = Field(min_length=1, max_length=500)
    confirm: bool


class SessionCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=200)
    agent_id: str


class SessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageRead(ApiModel):
    id: str
    role: str
    content: str
    citations: list[dict[str, Any]]
    created_at: datetime


class SessionRead(ApiModel):
    id: str
    title: str
    agent_id: str
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionRead):
    messages: list[MessageRead]


class RunCreate(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)


class RunAccepted(BaseModel):
    run_id: str
    status: str
    events_url: str


class Citation(BaseModel):
    document_id: str
    filename: str
    page: int | None
    chunk_index: int
    score: float


class RunRead(ApiModel):
    id: str
    session_id: str
    agent_id: str
    status: str
    input: str
    output: str
    error_code: str | None
    error_message: str | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunEventRead(ApiModel):
    id: int
    run_id: str
    type: str
    data: dict[str, Any]
    created_at: datetime


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=4000)


class ApprovalRead(ApiModel):
    id: str
    run_id: str
    tool_name: str
    arguments: dict[str, Any]
    risk: str
    status: str
    decision_reason: str | None
    created_at: datetime
    resolved_at: datetime | None


class CancelResponse(BaseModel):
    run_id: str
    status: str


class SystemStatus(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: str
    embedding_backend: str
    model_configured: bool
    active_runs: int
    interrupted_runs: int
    skills: int
    data_dir: str

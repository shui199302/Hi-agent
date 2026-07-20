"""Public API schemas."""

from __future__ import annotations

import re
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


class UserRead(ApiModel):
    id: str
    username: str
    phone: str | None
    role: str
    status: str
    wechat_nickname: str | None
    avatar_url: str | None
    created_at: datetime
    last_login_at: datetime | None


class AuthConfig(BaseModel):
    mode: Literal["development", "production"]
    mock_phone_enabled: bool
    mock_wechat_enabled: bool
    provider_notice: str


class OtpRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    purpose: Literal["register", "login"]


class OtpIssued(BaseModel):
    challenge_id: str
    expires_in: int
    resend_after: int
    debug_code: str | None = None


class PhoneRegister(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(pattern=r"^\d{6}$")
    username: str = Field(min_length=2, max_length=80)


class PhoneLogin(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(pattern=r"^\d{6}$")


class WechatChallengeCreate(BaseModel):
    purpose: Literal["register", "login"]


class WechatChallengeRead(BaseModel):
    challenge_id: str
    ticket: str
    status: str
    expires_in: int
    mock: bool


class WechatMockAuthorize(BaseModel):
    ticket: str = Field(min_length=20, max_length=300)
    nickname: str = Field(default="Hi-agent 微信用户", min_length=1, max_length=80)
    mock_account: str = Field(default="default", min_length=1, max_length=80)


class WechatComplete(BaseModel):
    ticket: str = Field(min_length=20, max_length=300)


class AuthResult(BaseModel):
    user: UserRead
    csrf_token: str


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


class ImageEndpointBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: AnyHttpUrl
    model: str = Field(min_length=1, max_length=250)
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,119}$")
    timeout_seconds: float = Field(default=180.0, ge=1, le=600)
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def secure_image_endpoint(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" and value.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("remote image endpoint must use HTTPS")
        return value


class ImageEndpointCreate(ImageEndpointBase):
    pass


class ImageEndpointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: AnyHttpUrl | None = None
    model: str | None = Field(default=None, min_length=1, max_length=250)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,119}$")
    timeout_seconds: float | None = Field(default=None, ge=1, le=600)
    enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def secure_image_endpoint(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and value.scheme != "https" and value.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("remote image endpoint must use HTTPS")
        return value


class ImageEndpointRead(ApiModel):
    id: str
    name: str
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "archived"] | None = None


class ProjectRead(ApiModel):
    id: str
    name: str
    description: str
    status: Literal["active", "archived"]
    agent_count: int = 0
    knowledge_base_count: int = 0
    session_count: int = 0
    run_count: int = 0
    last_activity_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProjectAgentAssign(BaseModel):
    agent_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("agent_ids")
    @classmethod
    def unique_agent_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("agent_ids must be unique")
        return value


class PromptTemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    category: Literal["general", "rag", "research", "analysis", "writing", "coding", "custom"] = "custom"
    content: str = Field(min_length=10, max_length=100_000)
    variables: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=30)
    enabled: bool = True

    @field_validator("variables")
    @classmethod
    def valid_variables(cls, value: list[str]) -> list[str]:
        invalid = any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", item) for item in value)
        if len(set(value)) != len(value) or invalid:
            raise ValueError("variables must be unique identifier names")
        return value


class PromptTemplateCreate(PromptTemplateBase):
    pass


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    category: Literal["general", "rag", "research", "analysis", "writing", "coding", "custom"] | None = None
    content: str | None = Field(default=None, min_length=10, max_length=100_000)
    variables: list[str] | None = Field(default=None, max_length=50)
    tags: list[str] | None = Field(default=None, max_length=30)
    enabled: bool | None = None

    @field_validator("variables")
    @classmethod
    def valid_variables(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        invalid = any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", item) for item in value)
        if len(set(value)) != len(value) or invalid:
            raise ValueError("variables must be unique identifier names")
        return value


class PromptTemplateRead(ApiModel):
    id: str
    name: str
    description: str
    category: str
    content: str
    variables: list[str]
    tags: list[str]
    builtin: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseBase(BaseModel):
    project_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", min_length=1, max_length=250)
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    top_k: int = Field(default=5, ge=1, le=50)
    ocr_mode: Literal["off", "auto", "force"] = "auto"
    ocr_language: Literal["ch", "en"] = "ch"
    ocr_min_chars: int = Field(default=30, ge=0, le=1000)

    @model_validator(mode="after")
    def overlap_is_smaller(self) -> KnowledgeBaseBase:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(BaseModel):
    project_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    ocr_mode: Literal["off", "auto", "force"] | None = None
    ocr_language: Literal["ch", "en"] | None = None
    ocr_min_chars: int | None = Field(default=None, ge=0, le=1000)


class KnowledgeBaseReindex(BaseModel):
    embedding_model: str = Field(min_length=1, max_length=250)
    chunk_size: int = Field(ge=100, le=4000)
    chunk_overlap: int = Field(ge=0, le=1000)
    top_k: int = Field(ge=1, le=50)
    ocr_mode: Literal["off", "auto", "force"] = "auto"
    ocr_language: Literal["ch", "en"] = "ch"
    ocr_min_chars: int = Field(default=30, ge=0, le=1000)

    @model_validator(mode="after")
    def overlap_is_smaller(self) -> KnowledgeBaseReindex:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class KnowledgeBaseRead(ApiModel):
    id: str
    project_id: str
    name: str
    description: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    ocr_mode: str
    ocr_language: str
    ocr_min_chars: int
    document_count: int = 0
    chunk_count: int = 0
    ready_document_count: int = 0
    processing_document_count: int = 0
    failed_document_count: int = 0
    total_size_bytes: int = 0
    bound_agent_count: int = 0
    status: Literal["empty", "ready", "processing", "error"] = "empty"
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
    extraction_method: str
    ocr_pages: list[int]
    ocr_engine: str | None
    created_at: datetime


class ArtifactRead(ApiModel):
    id: str
    project_id: str
    run_id: str | None
    kind: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime


class ArtifactReportCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500_000)
    format: Literal["md", "docx", "pdf"] = "md"


class ArtifactPresentationCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    slides: list[dict[str, Any]] = Field(min_length=1, max_length=30)


class ArtifactImageCreate(BaseModel):
    project_id: str
    image_endpoint_id: str | None = None
    prompt: str = Field(min_length=2, max_length=8000)


class ArtifactRunReportCreate(BaseModel):
    run_id: str
    format: Literal["md", "docx", "pdf"] = "pdf"


class KnowledgeBaseQueryResponse(BaseModel):
    items: list[KnowledgeBaseRead]
    total: int
    offset: int
    limit: int


class DocumentQueryResponse(BaseModel):
    items: list[DocumentRead]
    total: int
    offset: int
    limit: int


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
    description: str = Field(default="", max_length=1000)
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
    description: str | None = Field(default=None, max_length=1000)
    command: str | None = Field(default=None, max_length=500)
    args: list[str] | None = Field(default=None, max_length=100)
    url: AnyHttpUrl | None = None
    env_refs: dict[str, str] | None = None
    enabled: bool | None = None
    allow_remote: bool | None = None


class McpServerRead(ApiModel):
    id: str
    name: str
    description: str
    source_url: str | None
    setup_hint: str
    builtin: bool
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
    project_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    system_prompt: str = Field(default="你是一个可靠的中文智能体助手。", min_length=1, max_length=100_000)
    model_endpoint_id: str | None = None
    knowledge_base_id: str | None = None
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
    max_tool_loops: int = Field(default=12, ge=1, le=12)
    review_policy: Literal["off", "auto", "manual", "risk_based"] = "risk_based"
    review_model_endpoint_id: str | None = None
    review_max_rounds: int = Field(default=2, ge=0, le=3)
    enabled: bool = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    project_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=100_000)
    model_endpoint_id: str | None = None
    knowledge_base_id: str | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None
    tool_policy: dict[str, Any] | None = None
    max_tool_loops: int | None = Field(default=None, ge=1, le=12)
    review_policy: Literal["off", "auto", "manual", "risk_based"] | None = None
    review_model_endpoint_id: str | None = None
    review_max_rounds: int | None = Field(default=None, ge=0, le=3)
    enabled: bool | None = None


class AgentRead(ApiModel):
    id: str
    project_id: str
    name: str
    description: str
    system_prompt: str
    model_endpoint_id: str | None
    knowledge_base_id: str | None
    skills: list[str]
    mcp_servers: list[str]
    tool_policy: dict[str, Any]
    max_tool_loops: int
    review_policy: str
    review_model_endpoint_id: str | None
    review_max_rounds: int
    agent_type: str
    builtin: bool
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


class DigitalHumanGenerate(BaseModel):
    description: str = Field(min_length=2, max_length=1000)


class DigitalHumanSpec(BaseModel):
    version: int
    name: str
    presentation: Literal["feminine", "masculine", "neutral"]
    skin_tone: str
    hair_style: Literal["short", "long", "curly", "bun", "bald"]
    hair_color: str
    eye_color: str
    outfit: Literal["tshirt", "hoodie", "suit", "dress", "jacket"]
    outfit_color: str
    accent_color: str
    accessory: Literal["none", "glasses", "headphones", "earrings"]
    expression: Literal["smile", "calm", "confident", "cool"]
    background: str
    seed: int


class DigitalHumanGenerateResponse(BaseModel):
    agent_id: str
    agent_name: str
    description: str
    spec: DigitalHumanSpec


class SkillMetadata(BaseModel):
    name: str
    description: str
    directory: str
    has_scripts: bool
    scripts_allowed: bool
    valid: bool
    error: str | None = None
    source: str = "builtin"
    version: str | None = None
    publisher: str | None = None
    sha256: str | None = None


class SkillDetail(SkillMetadata):
    instructions: str
    references: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)


class RemoteSkillRead(BaseModel):
    source: Literal["github", "clawhub"] = "github"
    catalog: str = ""
    repository: str = ""
    ref: str = ""
    path: str = ""
    name: str
    description: str
    source_url: str
    has_scripts: bool = False
    license: str | None = None
    slug: str | None = None
    version: str | None = None
    publisher: str | None = None
    security_verdict: str | None = None
    downloads: int | None = None
    sha256: str | None = None
    instructions_preview: str | None = None


class RemoteSkillInstall(BaseModel):
    source: Literal["github", "clawhub"] = "github"
    catalog: str = Field(default="", max_length=200)
    path: str = Field(default="", max_length=500)
    slug: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=80)
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
    project_id: str
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
    project_id: str
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


class RagReportCreate(BaseModel):
    run_id: str
    format: Literal["md", "docx", "pdf"]


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
    kind: str
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

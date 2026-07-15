"""Persistent domain models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    interrupted = "interrupted"


ACTIVE_RUN_STATUSES = {
    RunStatus.queued.value,
    RunStatus.running.value,
    RunStatus.waiting_approval.value,
}


class ModelEndpoint(Base):
    __tablename__ = "model_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(250))
    api_key_env: Mapped[str] = mapped_column(String(120), default="HI_AGENT_LLM_API_KEY")
    timeout_seconds: Mapped[float] = mapped_column(Float, default=120.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(250), default="BAAI/bge-small-zh-v1.5")
    chunk_size: Mapped[int] = mapped_column(Integer, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=120)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    documents: Mapped[list[Document]] = relationship(back_populates="knowledge_base", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("knowledge_base_id", "sha256", name="uq_document_kb_sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="processing")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(800))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    vector_json: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class McpServerConfig(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    transport: Mapped[str] = mapped_column(String(30))
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    args: Mapped[list[str]] = mapped_column(JSON, default=list)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    env_refs: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class AgentConfig(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="你是一个可靠的中文智能体助手。")
    model_endpoint_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_endpoints.id", ondelete="SET NULL"), nullable=True
    )
    knowledge_base_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True
    )
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    mcp_servers: Mapped[list[str]] = mapped_column(JSON, default=list)
    tool_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    max_tool_loops: Mapped[int] = mapped_column(Integer, default=12)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ChatSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    runs: Mapped[list[Run]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_session_status", "session_id", "status"),
        Index(
            "uq_runs_one_active_per_session",
            "session_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running', 'waiting_approval')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30), default=RunStatus.queued.value)
    input: Mapped[str] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[ChatSession] = relationship(back_populates="runs")
    events: Mapped[list[RunEvent]] = relationship(back_populates="run", cascade="all, delete-orphan")
    approvals: Mapped[list[Approval]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_id_id", "run_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    run: Mapped[Run] = relationship(back_populates="events")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    tool_name: Mapped[str] = mapped_column(String(300))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[Run] = relationship(back_populates="approvals")


class RunCheckpoint(Base):
    __tablename__ = "run_checkpoints"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    node: Mapped[str] = mapped_column(String(80))
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

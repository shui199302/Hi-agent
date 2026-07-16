"""Versioned REST and resumable SSE API."""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import __version__
from .auth import CurrentUser, current_user, require_admin, require_csrf
from .database import get_db
from .errors import ConflictError, HiAgentError, NotFoundError
from .mcp_client import McpClient
from .models import (
    ACTIVE_RUN_STATUSES,
    AgentConfig,
    AgentRevision,
    Approval,
    ChatSession,
    Document,
    KnowledgeBase,
    McpServerConfig,
    Message,
    ModelEndpoint,
    Run,
    RunEvent,
    RunStatus,
    User,
    now_utc,
)
from .rag import RagService
from .runtime import RunManager, snapshot_agent
from .schemas import (
    AgentCreate,
    AgentRead,
    AgentRevisionRead,
    AgentUpdate,
    ApprovalDecision,
    ApprovalRead,
    CancelResponse,
    DocumentQueryResponse,
    DocumentRead,
    KnowledgeBaseCreate,
    KnowledgeBaseQueryResponse,
    KnowledgeBaseRead,
    KnowledgeBaseReindex,
    KnowledgeBaseUpdate,
    McpProbeResponse,
    McpServerCreate,
    McpServerRead,
    McpServerUpdate,
    ModelEndpointCreate,
    ModelEndpointRead,
    ModelEndpointUpdate,
    RemoteSkillInstall,
    RemoteSkillRead,
    RunAccepted,
    RunCreate,
    RunEventRead,
    RunRead,
    SearchRequest,
    SearchResponse,
    SessionCreate,
    SessionDetail,
    SessionRead,
    SessionUpdate,
    SkillCreateRequest,
    SkillDetail,
    SkillMetadata,
    SystemStatus,
)
from .skills import SkillRegistry

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user), Depends(require_csrf)])


def _get[ModelT](db: Session, model: type[ModelT], item_id: str, label: str) -> ModelT:
    item = db.get(model, item_id)
    if item is None:
        raise NotFoundError(label, item_id)
    return item


def _commit[ModelT](db: Session, item: ModelT) -> ModelT:
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _apply[ModelT](item: ModelT, payload: BaseModel) -> ModelT:
    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(item, key, value)
    return item


def _manager(request: Request) -> RunManager:
    return cast(RunManager, request.app.state.run_manager)


def _rag(request: Request) -> RagService:
    return cast(RagService, request.app.state.rag_service)


def _mcp(request: Request) -> McpClient:
    return cast(McpClient, request.app.state.mcp_client)


def _skills(request: Request) -> SkillRegistry:
    return cast(SkillRegistry, request.app.state.skill_registry)


def _owner_id(request: Request) -> str:
    return str(request.state.user.id)


def _validate_user_secret_reference(user: User, env_name: str) -> None:
    if user.role == "admin":
        return
    prefix = f"HI_AGENT_USER_{user.id.replace('-', '').upper()}_"
    if not env_name.startswith(prefix):
        raise HiAgentError(
            "SECRET_REFERENCE_FORBIDDEN",
            "普通用户只能引用分配给自己命名空间的环境变量",
            status_code=403,
            details={"required_prefix": prefix},
        )


def _knowledge_base_read(db: Session, kb: KnowledgeBase) -> KnowledgeBaseRead:
    document_count, chunk_count, ready_count, processing_count, failed_count, total_size = db.execute(
        select(
            func.count(Document.id),
            func.coalesce(func.sum(Document.chunk_count), 0),
            func.count(Document.id).filter(Document.status.in_(("ready", "indexed"))),
            func.count(Document.id).filter(Document.status == "processing"),
            func.count(Document.id).filter(Document.status.in_(("failed", "error"))),
            func.coalesce(func.sum(Document.size_bytes), 0),
        ).where(Document.knowledge_base_id == kb.id)
    ).one()
    bound_agent_count = db.scalar(
        select(func.count()).select_from(AgentConfig).where(AgentConfig.knowledge_base_id == kb.id)
    ) or 0
    kb_status = "empty"
    if failed_count:
        kb_status = "error"
    elif processing_count:
        kb_status = "processing"
    elif document_count:
        kb_status = "ready"
    return KnowledgeBaseRead.model_validate(kb).model_copy(
        update={
            "document_count": int(document_count),
            "chunk_count": int(chunk_count),
            "ready_document_count": int(ready_count),
            "processing_document_count": int(processing_count),
            "failed_document_count": int(failed_count),
            "total_size_bytes": int(total_size),
            "bound_agent_count": int(bound_agent_count),
            "status": kb_status,
        }
    )


def _agent_snapshot(agent: AgentConfig) -> dict[str, Any]:
    return {
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "model_endpoint_id": agent.model_endpoint_id,
        "knowledge_base_id": agent.knowledge_base_id,
        "skills": list(agent.skills),
        "mcp_servers": list(agent.mcp_servers),
        "tool_policy": dict(agent.tool_policy),
        "max_tool_loops": agent.max_tool_loops,
        "enabled": agent.enabled,
    }


def _save_agent_revision(db: Session, agent: AgentConfig, reason: str) -> None:
    latest = db.scalar(select(func.max(AgentRevision.version)).where(AgentRevision.agent_id == agent.id)) or 0
    db.add(AgentRevision(agent_id=agent.id, version=int(latest) + 1, snapshot=_agent_snapshot(agent), reason=reason))
    db.commit()


@router.get("/system/status", response_model=SystemStatus)
def system_status(request: Request, db: Session = Depends(get_db)) -> SystemStatus:
    active = db.scalar(select(func.count()).select_from(Run).where(Run.status.in_(ACTIVE_RUN_STATUSES))) or 0
    interrupted = db.scalar(select(func.count()).select_from(Run).where(Run.status == RunStatus.interrupted.value)) or 0
    settings = request.app.state.settings
    manager = _manager(request)
    return SystemStatus(
        status="ok",
        version=__version__,
        database="ok",
        embedding_backend=settings.embedding_backend,
        model_configured=bool(db.scalar(select(func.count()).select_from(ModelEndpoint).where(ModelEndpoint.enabled))),
        active_runs=active,
        interrupted_runs=interrupted,
        skills=len(manager.skills.list()),
        data_dir=str(settings.data_dir),
    )


@router.get("/models", response_model=list[ModelEndpointRead])
def list_models(db: Session = Depends(get_db)) -> list[ModelEndpoint]:
    return list(db.scalars(select(ModelEndpoint).order_by(ModelEndpoint.created_at)).all())


@router.post("/models", response_model=ModelEndpointRead, status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelEndpointCreate, user: CurrentUser, db: Session = Depends(get_db)) -> ModelEndpoint:
    _validate_user_secret_reference(user, payload.api_key_env)
    return _commit(db, ModelEndpoint(**payload.model_dump(mode="json")))


@router.get("/models/{model_id}", response_model=ModelEndpointRead)
def get_model(model_id: str, db: Session = Depends(get_db)) -> ModelEndpoint:
    return _get(db, ModelEndpoint, model_id, "ModelEndpoint")


@router.patch("/models/{model_id}", response_model=ModelEndpointRead)
def update_model(
    model_id: str, payload: ModelEndpointUpdate, user: CurrentUser, db: Session = Depends(get_db)
) -> ModelEndpoint:
    if payload.api_key_env:
        _validate_user_secret_reference(user, payload.api_key_env)
    return _commit(db, _apply(_get(db, ModelEndpoint, model_id, "ModelEndpoint"), payload))


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: str, db: Session = Depends(get_db)) -> Response:
    db.delete(_get(db, ModelEndpoint, model_id, "ModelEndpoint"))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(db: Session = Depends(get_db)) -> list[KnowledgeBaseRead]:
    items = db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at)).all()
    return [_knowledge_base_read(db, item) for item in items]


@router.get("/knowledge-bases/query", response_model=KnowledgeBaseQueryResponse)
def query_knowledge_bases(
    q: str = Query(default="", max_length=200),
    name_exact: str = Query(default="", max_length=120),
    status_filter: str = Query(default="all", alias="status", pattern=r"^(all|empty|ready|processing|error)$"),
    sort_by: str = Query(default="updated_at", pattern=r"^(name|created_at|updated_at|document_count)$"),
    sort_order: str = Query(default="desc", pattern=r"^(asc|desc)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> KnowledgeBaseQueryResponse:
    statement = select(KnowledgeBase)
    if name_exact:
        statement = statement.where(KnowledgeBase.name == name_exact)
    elif q.strip():
        pattern = f"%{q.strip().lower()}%"
        statement = statement.where(
            func.lower(KnowledgeBase.name).like(pattern) | func.lower(KnowledgeBase.description).like(pattern)
        )
    items = [_knowledge_base_read(db, item) for item in db.scalars(statement).all()]
    if status_filter != "all":
        items = [item for item in items if item.status == status_filter]
    reverse = sort_order == "desc"
    if sort_by == "document_count":
        items.sort(key=lambda item: (item.document_count, item.name.lower()), reverse=reverse)
    elif sort_by == "name":
        items.sort(key=lambda item: item.name.lower(), reverse=reverse)
    else:
        items.sort(key=lambda item: getattr(item, sort_by), reverse=reverse)
    total = len(items)
    return KnowledgeBaseQueryResponse(items=items[offset : offset + limit], total=total, offset=offset, limit=limit)


@router.post("/knowledge-bases", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    request: Request, payload: KnowledgeBaseCreate, db: Session = Depends(get_db)
) -> KnowledgeBaseRead:
    values = payload.model_dump()
    if "embedding_model" not in payload.model_fields_set:
        values["embedding_model"] = request.app.state.settings.embedding_model
    return _knowledge_base_read(db, _commit(db, KnowledgeBase(**values)))


@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base(kb_id: str, db: Session = Depends(get_db)) -> KnowledgeBaseRead:
    return _knowledge_base_read(db, _get(db, KnowledgeBase, kb_id, "KnowledgeBase"))


@router.patch("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(kb_id: str, payload: KnowledgeBaseUpdate, db: Session = Depends(get_db)) -> KnowledgeBaseRead:
    kb = _commit(db, _apply(_get(db, KnowledgeBase, kb_id, "KnowledgeBase"), payload))
    return _knowledge_base_read(db, kb)


@router.post("/knowledge-bases/{kb_id}/reindex", response_model=KnowledgeBaseRead)
def reindex_knowledge_base(
    request: Request, kb_id: str, payload: KnowledgeBaseReindex, db: Session = Depends(get_db)
) -> KnowledgeBaseRead:
    kb = _get(db, KnowledgeBase, kb_id, "KnowledgeBase")
    rebuilt = _rag(request).reindex(db, kb, **payload.model_dump())
    return _knowledge_base_read(db, rebuilt)


@router.delete("/knowledge-bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(request: Request, kb_id: str, db: Session = Depends(get_db)) -> Response:
    kb = _get(db, KnowledgeBase, kb_id, "KnowledgeBase")
    documents = list(db.scalars(select(Document).where(Document.knowledge_base_id == kb_id)).all())
    for document in documents:
        _rag(request).delete_document(db, document)
    db.delete(kb)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents", response_model=list[DocumentRead])
def list_all_documents(db: Session = Depends(get_db)) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.created_at.desc())).all())


@router.get("/knowledge-bases/{kb_id}/documents", response_model=list[DocumentRead])
def list_documents(kb_id: str, db: Session = Depends(get_db)) -> list[Document]:
    _get(db, KnowledgeBase, kb_id, "KnowledgeBase")
    return list(
        db.scalars(
            select(Document).where(Document.knowledge_base_id == kb_id).order_by(Document.created_at.desc())
        ).all()
    )


@router.get("/knowledge-bases/{kb_id}/documents/query", response_model=DocumentQueryResponse)
def query_documents(
    kb_id: str,
    q: str = Query(default="", max_length=255),
    filename_exact: str = Query(default="", max_length=255),
    status_filter: str = Query(default="all", alias="status", pattern=r"^(all|processing|ready|indexed|failed|error)$"),
    sort_by: str = Query(default="created_at", pattern=r"^(filename|created_at|size_bytes|chunk_count)$"),
    sort_order: str = Query(default="desc", pattern=r"^(asc|desc)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> DocumentQueryResponse:
    _get(db, KnowledgeBase, kb_id, "KnowledgeBase")
    statement = select(Document).where(Document.knowledge_base_id == kb_id)
    if filename_exact:
        statement = statement.where(Document.filename == filename_exact)
    elif q.strip():
        statement = statement.where(func.lower(Document.filename).like(f"%{q.strip().lower()}%"))
    if status_filter != "all":
        statuses = ("failed", "error") if status_filter in {"failed", "error"} else (status_filter,)
        statement = statement.where(Document.status.in_(statuses))
    sort_column = getattr(Document, sort_by)
    statement = statement.order_by(sort_column.desc() if sort_order == "desc" else sort_column.asc(), Document.id)
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    items = [DocumentRead.model_validate(item) for item in db.scalars(statement.offset(offset).limit(limit)).all()]
    return DocumentQueryResponse(items=items, total=int(total), offset=offset, limit=limit)


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    kb_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    _get(db, KnowledgeBase, kb_id, "KnowledgeBase")
    maximum = request.app.state.settings.upload_max_bytes
    content = await file.read(maximum + 1)
    if len(content) > maximum:
        raise HiAgentError(
            "UPLOAD_TOO_LARGE",
            "上传文件超过 50MB 限制",
            status_code=413,
            details={"max_bytes": maximum},
        )
    rag_service = _rag(request)
    filename = file.filename or ""
    media_type = file.content_type or "application/octet-stream"

    def ingest_in_worker() -> Document:
        with session_factory_for_request()() as worker_db:
            worker_db.info["owner_id"] = _owner_id(request)
            worker_kb = _get(worker_db, KnowledgeBase, kb_id, "KnowledgeBase")
            document = rag_service.ingest(
                worker_db,
                worker_kb,
                filename,
                media_type,
                content,
            )
            worker_db.expunge(document)
            return document

    return await asyncio.to_thread(ingest_in_worker)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: str, db: Session = Depends(get_db)) -> Document:
    return _get(db, Document, document_id, "Document")


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(request: Request, document_id: str, db: Session = Depends(get_db)) -> Response:
    _rag(request).delete_document(db, _get(db, Document, document_id, "Document"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/knowledge-bases/{kb_id}/search", response_model=SearchResponse)
def search_knowledge_base(
    request: Request,
    kb_id: str,
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    kb = _get(db, KnowledgeBase, kb_id, "KnowledgeBase")
    return SearchResponse(
        items=_rag(request).search(db, kb, payload.query, payload.top_k, payload.mode),
        mode=payload.mode,
        query=payload.query,
    )


def _validate_agent(
    request: Request,
    db: Session,
    payload: AgentCreate | AgentUpdate,
) -> None:
    data = payload.model_dump(exclude_unset=True)
    if endpoint_id := data.get("model_endpoint_id"):
        _get(db, ModelEndpoint, endpoint_id, "ModelEndpoint")
    if kb_id := data.get("knowledge_base_id"):
        _get(db, KnowledgeBase, kb_id, "KnowledgeBase")
    for server_id in data.get("mcp_servers") or []:
        _get(db, McpServerConfig, server_id, "McpServer")
    available_skills = {item.name for item in _skills(request).list() if item.valid}
    invalid_skills = sorted(set(data.get("skills") or []) - available_skills)
    if invalid_skills:
        raise HiAgentError(
            "SKILL_NOT_FOUND_OR_INVALID",
            "Agent 引用了不存在或无效的 Skill",
            details={"skills": invalid_skills},
        )


@router.get("/agents", response_model=list[AgentRead])
def list_agents(db: Session = Depends(get_db)) -> list[AgentConfig]:
    return list(db.scalars(select(AgentConfig).order_by(AgentConfig.created_at)).all())


@router.post("/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(
    request: Request,
    payload: AgentCreate,
    db: Session = Depends(get_db),
) -> AgentConfig:
    _validate_agent(request, db, payload)
    agent = _commit(db, AgentConfig(**payload.model_dump()))
    _save_agent_revision(db, agent, "创建智能体")
    return agent


@router.get("/agents/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentConfig:
    return _get(db, AgentConfig, agent_id, "Agent")


@router.patch("/agents/{agent_id}", response_model=AgentRead)
def update_agent(
    request: Request,
    agent_id: str,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
) -> AgentConfig:
    _validate_agent(request, db, payload)
    agent = _commit(db, _apply(_get(db, AgentConfig, agent_id, "Agent"), payload))
    _save_agent_revision(db, agent, "配置更新")
    return agent


@router.get("/agents/{agent_id}/revisions", response_model=list[AgentRevisionRead])
def list_agent_revisions(agent_id: str, db: Session = Depends(get_db)) -> list[AgentRevision]:
    _get(db, AgentConfig, agent_id, "Agent")
    return list(
        db.scalars(
            select(AgentRevision).where(AgentRevision.agent_id == agent_id).order_by(AgentRevision.version.desc())
        ).all()
    )


@router.post("/agents/{agent_id}/revisions/{revision_id}/restore", response_model=AgentRead)
def restore_agent_revision(
    request: Request, agent_id: str, revision_id: str, db: Session = Depends(get_db)
) -> AgentConfig:
    agent = _get(db, AgentConfig, agent_id, "Agent")
    revision = _get(db, AgentRevision, revision_id, "AgentRevision")
    if revision.agent_id != agent_id:
        raise NotFoundError("AgentRevision", revision_id)
    payload = AgentUpdate.model_validate(revision.snapshot)
    _validate_agent(request, db, payload)
    agent = _commit(db, _apply(agent, payload))
    _save_agent_revision(db, agent, f"恢复版本 {revision.version}")
    return agent


@router.get("/observability/summary")
def observability_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    runs = list(db.scalars(select(Run).order_by(Run.created_at.desc()).limit(100)).all())
    status_counts = Counter(run.status for run in runs)
    completed = [run for run in runs if run.started_at and run.finished_at]
    durations = [
        (run.finished_at - run.started_at).total_seconds() for run in completed if run.finished_at and run.started_at
    ]
    recent = []
    for run in runs[:20]:
        events = list(db.scalars(select(RunEvent).where(RunEvent.run_id == run.id)).all())
        retrieval_hits = sum(len(event.data.get("items", [])) for event in events if event.type == "retrieval")
        recent.append(
            {
                "id": run.id,
                "agent_id": run.agent_id,
                "status": run.status,
                "duration_seconds": (run.finished_at - run.started_at).total_seconds()
                if run.finished_at and run.started_at
                else None,
                "tool_calls": sum(event.type == "tool_call" for event in events),
                "retrieval_hits": retrieval_hits,
                "error_code": run.error_code,
                "created_at": run.created_at,
            }
        )
    return {
        "total_runs": len(runs),
        "status_counts": dict(status_counts),
        "average_duration_seconds": sum(durations) / len(durations) if durations else 0,
        "recent_runs": recent,
    }


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, db: Session = Depends(get_db)) -> Response:
    agent = _get(db, AgentConfig, agent_id, "Agent")
    in_use = db.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.agent_id == agent_id))
    if in_use:
        raise ConflictError("AGENT_IN_USE", "已有会话使用该 Agent", sessions=in_use)
    db.delete(agent)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/mcp/servers", response_model=list[McpServerRead])
def list_mcp_servers(db: Session = Depends(get_db)) -> list[McpServerConfig]:
    return list(db.scalars(select(McpServerConfig).order_by(McpServerConfig.created_at)).all())


@router.post("/mcp/servers", response_model=McpServerRead, status_code=status.HTTP_201_CREATED)
def create_mcp_server(payload: McpServerCreate, user: CurrentUser, db: Session = Depends(get_db)) -> McpServerConfig:
    if user.role != "admin" and (payload.transport == "stdio" or payload.env_refs):
        raise HiAgentError(
            "MCP_CONFIG_FORBIDDEN",
            "普通用户只能创建不含环境变量的 Streamable HTTP MCP 配置",
            status_code=403,
        )
    return _commit(db, McpServerConfig(**payload.model_dump(mode="json")))


@router.get("/mcp/servers/{server_id}", response_model=McpServerRead)
def get_mcp_server(server_id: str, db: Session = Depends(get_db)) -> McpServerConfig:
    return _get(db, McpServerConfig, server_id, "McpServer")


@router.patch("/mcp/servers/{server_id}", response_model=McpServerRead)
def update_mcp_server(
    server_id: str, payload: McpServerUpdate, user: CurrentUser, db: Session = Depends(get_db)
) -> McpServerConfig:
    if user.role != "admin" and payload.env_refs:
        raise HiAgentError("MCP_CONFIG_FORBIDDEN", "普通用户不能配置 MCP 环境变量", status_code=403)
    server = _get(db, McpServerConfig, server_id, "McpServer")
    updated = _apply(server, payload)
    if updated.transport == "stdio" and not updated.command:
        raise HiAgentError("MCP_INVALID_CONFIG", "stdio MCP 缺少 command")
    if updated.transport == "streamable_http" and not updated.url:
        raise HiAgentError("MCP_INVALID_CONFIG", "streamable_http MCP 缺少 url")
    return _commit(db, updated)


@router.delete("/mcp/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mcp_server(server_id: str, db: Session = Depends(get_db)) -> Response:
    db.delete(_get(db, McpServerConfig, server_id, "McpServer"))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mcp/servers/{server_id}/probe", response_model=McpProbeResponse)
async def probe_mcp_server(request: Request, server_id: str, db: Session = Depends(get_db)) -> McpProbeResponse:
    server = _get(db, McpServerConfig, server_id, "McpServer")
    try:
        tools = await _mcp(request).list_tools(server)
        server.status = "online"
        server.last_error = None
        _commit(db, server)
        return McpProbeResponse(status="online", tools=tools)
    except HiAgentError as exc:
        server.status = "error"
        server.last_error = exc.message
        _commit(db, server)
        return McpProbeResponse(status="error", error=exc.message)


@router.get("/skills", response_model=list[SkillMetadata])
def list_skills(request: Request) -> list[SkillMetadata]:
    return _skills(request).list()


@router.get("/skills/{skill_name}", response_model=SkillDetail)
def get_skill(request: Request, skill_name: str) -> SkillDetail:
    return _skills(request).get(skill_name)


@router.get("/skills-remote/search", response_model=list[RemoteSkillRead])
def search_remote_skills(request: Request, q: str = Query(min_length=2, max_length=120)) -> list[RemoteSkillRead]:
    return _skills(request).search_remote(q)


@router.post("/skills-remote/install", response_model=SkillMetadata, status_code=status.HTTP_201_CREATED)
def install_remote_skill(
    request: Request, payload: RemoteSkillInstall, _: User = Depends(require_admin)
) -> SkillMetadata:
    return _skills(request).install_remote(
        payload.catalog, payload.path, confirm=payload.confirm, replace=payload.replace
    )


@router.post("/skills", response_model=SkillMetadata, status_code=status.HTTP_201_CREATED)
def create_skill(request: Request, payload: SkillCreateRequest, _: User = Depends(require_admin)) -> SkillMetadata:
    return _skills(request).create_skill(payload)


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(db: Session = Depends(get_db)) -> list[ChatSession]:
    return list(db.scalars(select(ChatSession).order_by(ChatSession.updated_at.desc())).all())


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> ChatSession:
    agent = _get(db, AgentConfig, payload.agent_id, "Agent")
    if not agent.enabled:
        raise HiAgentError("AGENT_DISABLED", "Agent 已禁用")
    return _commit(db, ChatSession(**payload.model_dump()))


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, db: Session = Depends(get_db)) -> ChatSession:
    return _get(db, ChatSession, session_id, "Session")


@router.patch("/sessions/{session_id}", response_model=SessionRead)
def update_session(session_id: str, payload: SessionUpdate, db: Session = Depends(get_db)) -> ChatSession:
    return _commit(db, _apply(_get(db, ChatSession, session_id, "Session"), payload))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, db: Session = Depends(get_db)) -> Response:
    session = _get(db, ChatSession, session_id, "Session")
    active = db.scalar(
        select(func.count()).select_from(Run).where(Run.session_id == session_id, Run.status.in_(ACTIVE_RUN_STATUSES))
    )
    if active:
        raise ConflictError("SESSION_HAS_ACTIVE_RUN", "会话仍有活动 Run")
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/runs",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    request: Request,
    session_id: str,
    payload: RunCreate,
    db: Session = Depends(get_db),
) -> RunAccepted:
    chat_session = _get(db, ChatSession, session_id, "Session")
    active = db.scalar(select(Run).where(Run.session_id == session_id, Run.status.in_(ACTIVE_RUN_STATUSES)))
    if active:
        raise ConflictError("SESSION_RUN_CONFLICT", "每个会话同时只允许一个活动 Run", run_id=active.id)
    agent = _get(db, AgentConfig, chat_session.agent_id, "Agent")
    if not agent.enabled:
        raise HiAgentError("AGENT_DISABLED", "Agent 已禁用")
    snapshot = snapshot_agent(db, agent)
    run = Run(
        session_id=session_id,
        agent_id=agent.id,
        input=payload.message,
        status=RunStatus.queued.value,
        config_snapshot=snapshot,
    )
    db.add(run)
    db.add(Message(session_id=session_id, role="user", content=payload.message))
    chat_session.updated_at = now_utc()
    db.commit()
    db.refresh(run)
    await _manager(request).start(run.id)
    return RunAccepted(
        run_id=run.id,
        status=run.status,
        events_url=f"/api/v1/runs/{run.id}/events",
    )


@router.get("/runs", response_model=list[RunRead])
def list_runs(session_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[Run]:
    statement = select(Run).order_by(Run.created_at.desc())
    if session_id:
        statement = statement.where(Run.session_id == session_id)
    return list(db.scalars(statement).all())


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> Run:
    return _get(db, Run, run_id, "Run")


@router.get("/runs/{run_id}/event-log", response_model=list[RunEventRead])
def get_run_events(
    run_id: str,
    after: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[RunEvent]:
    _get(db, Run, run_id, "Run")
    return list(
        db.scalars(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.id > after).order_by(RunEvent.id)).all()
    )


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    request: Request,
    run_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    with session_factory_for_request()() as db:
        db.info["owner_id"] = _owner_id(request)
        _get(db, Run, run_id, "Run")
    cursor = after
    if last_event_id:
        try:
            cursor = max(cursor, int(last_event_id))
        except ValueError:
            raise HiAgentError("INVALID_LAST_EVENT_ID", "Last-Event-ID 必须为整数") from None

    async def events() -> AsyncIterator[str]:
        nonlocal cursor
        last_heartbeat = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            with session_factory_for_request()() as db:
                db.info["owner_id"] = _owner_id(request)
                items = db.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.id > cursor)
                    .order_by(RunEvent.id)
                    .limit(250)
                ).all()
                run = db.get(Run, run_id)
                terminal = run is None or run.status not in ACTIVE_RUN_STATUSES
            for item in items:
                cursor = item.id
                payload = RunEventRead.model_validate(item).model_dump(mode="json")
                yield (f"id: {item.id}\nevent: {item.type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n")
            if terminal and not items:
                return
            if time.monotonic() - last_heartbeat >= request.app.state.settings.sse_heartbeat_seconds:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(request.app.state.settings.event_poll_seconds)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def session_factory_for_request() -> Any:
    # Import here keeps the API dependency override-friendly while SSE outlives a request dependency.
    from .database import session_factory

    return session_factory()


@router.post("/runs/{run_id}/cancel", response_model=CancelResponse)
async def cancel_run(request: Request, run_id: str, db: Session = Depends(get_db)) -> CancelResponse:
    _get(db, Run, run_id, "Run")
    result = await _manager(request).cancel(run_id)
    return CancelResponse(run_id=run_id, status=result)


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalRead])
def list_approvals(run_id: str, db: Session = Depends(get_db)) -> list[Approval]:
    _get(db, Run, run_id, "Run")
    return list(db.scalars(select(Approval).where(Approval.run_id == run_id).order_by(Approval.created_at)).all())


@router.post("/runs/{run_id}/approvals/{approval_id}", response_model=ApprovalRead)
async def decide_approval(
    request: Request,
    run_id: str,
    approval_id: str,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
) -> Approval:
    _get(db, Run, run_id, "Run")
    return await _manager(request).resume(
        run_id,
        approval_id,
        payload.decision,
        payload.reason,
    )

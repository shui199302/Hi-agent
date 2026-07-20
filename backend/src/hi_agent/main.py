"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from . import __version__
from .agent_config import revision_snapshot
from .api import router
from .auth import public_auth_router
from .config import Settings, get_settings
from .database import (
    configure_database,
    create_schema,
    ensure_builtin_agents,
    ensure_builtin_prompt_templates,
    ensure_default_project,
    initialize_tenancy,
    session_factory,
)
from .errors import HiAgentError
from .mcp_client import McpClient
from .mcp_presets import ensure_builtin_mcp_presets
from .models import AgentConfig, AgentRevision, ModelEndpoint, User
from .rag import RagService
from .runtime import RunManager
from .skills import SkillRegistry


def _seed_defaults(settings: Settings, owner_id: str) -> None:
    """Create a usable first agent without inventing a cloud fallback."""

    from sqlalchemy import select

    with session_factory()() as db:
        project_id = ensure_default_project(db, owner_id)
        for existing_owner_id in db.scalars(select(User.id)).all():
            ensure_builtin_prompt_templates(db, str(existing_owner_id))
        if db.scalar(select(AgentConfig).where(AgentConfig.agent_type == "general").limit(1)) is None:
            endpoint = None
            if settings.llm_model:
                endpoint = ModelEndpoint(
                    owner_id=owner_id,
                    name="环境变量模型",
                    base_url=settings.llm_base_url,
                    model=settings.llm_model,
                    api_key_env=settings.llm_api_key_env,
                )
                db.add(endpoint)
                db.flush()
            db.add(
                AgentConfig(
                    owner_id=owner_id,
                    project_id=project_id,
                    name="默认助手",
                    description="Hi-agent 默认本地助手",
                    model_endpoint_id=endpoint.id if endpoint else None,
                )
            )
        for existing_owner_id in db.scalars(select(User.id)).all():
            ensure_builtin_agents(db, str(existing_owner_id))
        ensure_builtin_mcp_presets(db, settings, owner_id)
        db.flush()
        for agent in db.scalars(select(AgentConfig)).all():
            if db.scalar(select(AgentRevision).where(AgentRevision.agent_id == agent.id).limit(1)) is None:
                db.add(
                    AgentRevision(
                        agent_id=agent.id,
                        version=1,
                        snapshot=revision_snapshot(agent),
                        reason="现有配置基线",
                    )
                )
        db.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_database(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        create_schema()
        owner_id = initialize_tenancy(settings)
        _seed_defaults(settings, owner_id)
        manager = RunManager(settings)
        await manager.initialize()
        app.state.settings = settings
        app.state.rag_service = manager.rag
        app.state.skill_registry = manager.skills
        app.state.mcp_client = manager.mcp
        app.state.run_manager = manager
        manager.mark_interrupted_runs()
        yield
        await manager.shutdown()

    app = FastAPI(
        title="Hi-agent API",
        version=__version__,
        description="Local-first LangGraph, RAG, MCP and Agent Skills runtime",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.rag_service = RagService(settings)
    app.state.skill_registry = SkillRegistry(settings)
    app.state.mcp_client = McpClient(settings)
    app.state.run_manager = RunManager(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID", "X-CSRF-Token"],
    )

    @app.get("/api/v1/health", tags=["系统"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(public_auth_router)
    app.include_router(router)

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def unknown_api(path: str) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "API_NOT_FOUND",
                    "message": "API 路径不存在",
                    "details": {"path": f"/api/{path}"},
                }
            },
        )

    @app.exception_handler(HiAgentError)
    async def hi_agent_error(_: Request, exc: HiAgentError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "RESOURCE_CONFLICT",
                    "message": "资源名称或唯一字段已存在，或仍被其他资源引用",
                    "details": {},
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数无效",
                    "details": {"issues": jsonable_encoder(exc.errors())},
                }
            },
        )

    dist = settings.web_dist_dir
    if dist.is_dir() and (dist / "index.html").is_file():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            requested = (dist / path).resolve()
            if path and requested.is_relative_to(dist.resolve()) and requested.is_file():
                return FileResponse(requested)
            return FileResponse(dist / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> dict[str, str]:
            return {"name": "Hi-agent", "api": "/docs", "status": "/api/v1/system/status"}

    return app


app = create_app()

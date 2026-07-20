"""Tenant-scoped content generation and artifact download routes."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api_support import get_owned, request_owner_id
from .artifacts import ArtifactService
from .database import get_db
from .errors import ConflictError
from .models import ACTIVE_RUN_STATUSES, Artifact, ImageEndpoint, Project, Run, RunEvent
from .schemas import (
    ArtifactImageCreate,
    ArtifactPresentationCreate,
    ArtifactRead,
    ArtifactReportCreate,
    ArtifactRunReportCreate,
)

router = APIRouter()


def _service(request: Request) -> ArtifactService:
    return ArtifactService(request.app.state.settings)


def _run_report_content(run: Run, event_counts: Counter[str]) -> str:
    agent = run.config_snapshot.get("agent") or {}
    model = run.config_snapshot.get("model_endpoint") or {}
    knowledge_base = run.config_snapshot.get("knowledge_base") or {}
    trace = "\n".join(f"- {name}: {count}" for name, count in sorted(event_counts.items())) or "- 无事件"
    content = (
        f"## 运行概览\n\n"
        f"- Run ID: `{run.id}`\n"
        f"- 状态: {run.status}\n"
        f"- 智能体: {agent.get('name') or run.agent_id}\n"
        f"- 模型: {model.get('name') or model.get('model') or '未记录'}\n"
        f"- 知识库: {knowledge_base.get('name') or '未使用'}\n"
        f"- 创建时间: {run.created_at.isoformat()}\n\n"
        f"## 用户输入\n\n{run.input}\n\n"
        f"## 智能体输出\n\n{run.output or '无输出'}\n\n"
        f"## Trace 事件统计\n\n{trace}\n"
    )
    if run.error_code or run.error_message:
        content += f"\n## 错误\n\n- 错误码: {run.error_code or '未记录'}\n- 信息: {run.error_message or '未记录'}\n"
    return content


@router.get("/artifacts", response_model=list[ArtifactRead])
def list_artifacts(
    project_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Artifact]:
    statement = select(Artifact).order_by(Artifact.created_at.desc())
    if project_id:
        get_owned(db, Project, project_id, "Project")
        statement = statement.where(Artifact.project_id == project_id)
    if run_id:
        get_owned(db, Run, run_id, "Run")
        statement = statement.where(Artifact.run_id == run_id)
    return list(db.scalars(statement).all())


@router.post("/artifacts/reports", response_model=ArtifactRead, status_code=status.HTTP_201_CREATED)
def create_report(request: Request, payload: ArtifactReportCreate, db: Session = Depends(get_db)) -> Artifact:
    get_owned(db, Project, payload.project_id, "Project")
    return _service(request).create_report(
        db,
        owner_id=request_owner_id(request),
        project_id=payload.project_id,
        title=payload.title,
        content=payload.content,
        output_format=payload.format,
    )


@router.post("/artifacts/presentations", response_model=ArtifactRead, status_code=status.HTTP_201_CREATED)
def create_presentation(
    request: Request, payload: ArtifactPresentationCreate, db: Session = Depends(get_db)
) -> Artifact:
    get_owned(db, Project, payload.project_id, "Project")
    return _service(request).create_presentation(
        db,
        owner_id=request_owner_id(request),
        project_id=payload.project_id,
        title=payload.title,
        slides=payload.slides,
    )


@router.post("/artifacts/images", response_model=ArtifactRead, status_code=status.HTTP_201_CREATED)
async def create_image(request: Request, payload: ArtifactImageCreate, db: Session = Depends(get_db)) -> Artifact:
    get_owned(db, Project, payload.project_id, "Project")
    endpoint = (
        get_owned(db, ImageEndpoint, payload.image_endpoint_id, "ImageEndpoint")
        if payload.image_endpoint_id
        else db.scalar(select(ImageEndpoint).where(ImageEndpoint.enabled.is_(True)).order_by(ImageEndpoint.created_at))
    )
    if endpoint is None:
        raise ConflictError("IMAGE_ENDPOINT_REQUIRED", "请先在设置中配置并启用图片生成端点")
    if not endpoint.enabled:
        raise ConflictError("IMAGE_ENDPOINT_DISABLED", "所选图片生成端点已停用")
    return await _service(request).create_image(
        db,
        owner_id=request_owner_id(request),
        project_id=payload.project_id,
        prompt=payload.prompt,
        endpoint=endpoint,
    )


@router.post("/artifacts/run-reports", response_model=ArtifactRead, status_code=status.HTTP_201_CREATED)
def create_run_report(request: Request, payload: ArtifactRunReportCreate, db: Session = Depends(get_db)) -> Artifact:
    run = get_owned(db, Run, payload.run_id, "Run")
    if run.status in ACTIVE_RUN_STATUSES:
        raise ConflictError("RUN_REPORT_NOT_TERMINAL", "运行尚未结束，暂时不能生成报告")
    event_types = db.scalars(select(RunEvent.type).where(RunEvent.run_id == run.id)).all()
    return _service(request).create_report(
        db,
        owner_id=request_owner_id(request),
        project_id=run.project_id,
        run_id=run.id,
        title=f"智能体运行报告-{run.id[:8]}",
        content=_run_report_content(run, Counter(event_types)),
        output_format=payload.format,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRead)
def get_artifact(artifact_id: str, db: Session = Depends(get_db)) -> Artifact:
    return get_owned(db, Artifact, artifact_id, "Artifact")


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(request: Request, artifact_id: str, db: Session = Depends(get_db)) -> FileResponse:
    artifact = get_owned(db, Artifact, artifact_id, "Artifact")
    path = _service(request).resolve_download(artifact)
    return FileResponse(
        path,
        filename=artifact.filename,
        media_type=artifact.media_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )

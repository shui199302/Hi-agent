#!/usr/bin/env python3
"""Verify real FastEmbed + local Qdrant indexing, citations, and vector deletion."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hi_agent.config import Settings
from hi_agent.database import configure_database, create_schema, reset_database_state, session_factory
from hi_agent.models import KnowledgeBase
from hi_agent.rag import RagService


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    model_cache = project_root / "data" / "models"
    if not model_cache.is_dir():
        raise SystemExit("真实嵌入模型尚未安装；请先运行 scripts/preload_embedding.py")

    with tempfile.TemporaryDirectory(prefix="hi-agent-real-rag-") as temporary:
        temp = Path(temporary)
        settings = Settings(
            data_dir=project_root / "data",
            database_url=f"sqlite:///{temp / 'metadata.sqlite3'}",
            qdrant_path=temp / "qdrant",
            embedding_backend="fastembed",
            embedding_model="BAAI/bge-small-zh-v1.5",
        )
        configure_database(settings)
        create_schema()
        service = RagService(settings)
        upload_directory: Path | None = None
        try:
            with session_factory()() as db:
                kb = KnowledgeBase(
                    name="真实嵌入验收",
                    embedding_model=settings.embedding_model,
                    chunk_size=100,
                    chunk_overlap=20,
                    top_k=5,
                )
                db.add(kb)
                db.commit()
                db.refresh(kb)
                document = service.ingest(
                    db,
                    kb,
                    "acceptance.md",
                    "text/markdown",
                    "# 海风计划\n\n海风计划的验收口令是青竹-427。该口令仅用于本地 RAG 检索测试。".encode(),
                )
                upload_directory = Path(document.storage_path).parent
                hits = service.search(db, kb, "海风计划的验收口令是什么？", 5)
                if not hits or "青竹-427" not in hits[0].content:
                    raise RuntimeError("真实中文嵌入未检索到预期片段")
                first = hits[0]
                if first.filename != "acceptance.md" or first.chunk_index != 0:
                    raise RuntimeError("RAG 引用缺少正确文件名或块编号")
                service.delete_document(db, document)
                if service.search(db, kb, "青竹-427", 5):
                    raise RuntimeError("删除文档后 Qdrant 仍返回已删除向量")
                db.delete(kb)
                db.commit()
                print(
                    "Real RAG smoke OK: BAAI/bge-small-zh-v1.5 + Qdrant; "
                    f"citation={first.filename}#chunk-{first.chunk_index}; score={first.score:.4f}"
                )
        finally:
            qdrant = service._qdrant
            if qdrant is not None and hasattr(qdrant, "close"):
                qdrant.close()
            reset_database_state()
            if upload_directory is not None and upload_directory.is_dir():
                try:
                    upload_directory.rmdir()
                except OSError:
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

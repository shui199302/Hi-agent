"""SQLAlchemy engine and transaction helpers."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, ORMExecuteState, Session, sessionmaker, with_loader_criteria

from .config import Settings, get_settings

if TYPE_CHECKING:
    from .models import AgentConfig


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def configure_database(settings: Settings | None = None) -> Engine:
    global _engine, _session_factory
    settings = settings or get_settings()
    settings.ensure_directories()
    if _engine is not None:
        _engine.dispose()
    connect_args = {"check_same_thread": False, "timeout": 30} if settings.sqlite_url.startswith("sqlite") else {}
    engine = create_engine(settings.sqlite_url, connect_args=connect_args, future=True)

    if settings.sqlite_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    _engine = engine
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    return engine


@event.listens_for(Session, "before_flush")
def _assign_owner(session: Session, *_: object) -> None:
    owner_id = session.info.get("owner_id")
    for item in session.new:
        if owner_id and hasattr(item, "owner_id") and not getattr(item, "owner_id", None):
            item.owner_id = owner_id  # type: ignore[attr-defined]
        if (
            owner_id
            and item.__class__.__name__ in {"AgentConfig", "KnowledgeBase"}
            and not getattr(item, "project_id", None)
        ):
            item.project_id = ensure_default_project(session, owner_id)  # type: ignore[attr-defined]
    new_agents = {
        item.id: item.project_id
        for item in session.new
        if item.__class__.__name__ == "AgentConfig" and getattr(item, "project_id", None)
    }
    new_sessions = {
        item.id: item.project_id
        for item in session.new
        if item.__class__.__name__ == "ChatSession" and getattr(item, "project_id", None)
    }
    from .models import AgentConfig, ChatSession

    for item in session.new:
        if item.__class__.__name__ == "ChatSession" and not getattr(item, "project_id", None):
            project_id = new_agents.get(item.agent_id)
            if not project_id:
                agent = session.get(AgentConfig, item.agent_id)
                project_id = agent.project_id if agent else None
            item.project_id = project_id  # type: ignore[attr-defined]
            if project_id:
                new_sessions[item.id] = project_id
        elif item.__class__.__name__ == "Run" and not getattr(item, "project_id", None):
            project_id = new_sessions.get(item.session_id)
            if not project_id:
                chat = session.get(ChatSession, item.session_id)
                project_id = chat.project_id if chat else None
            item.project_id = project_id  # type: ignore[attr-defined]


@event.listens_for(Session, "do_orm_execute")
def _filter_owned_rows(state: ORMExecuteState) -> None:
    owner_id = state.session.info.get("owner_id")
    if not owner_id or not state.is_select or state.execution_options.get("skip_owner_filter"):
        return
    from .models import (
        AgentConfig,
        Artifact,
        ChatSession,
        Document,
        ImageEndpoint,
        KnowledgeBase,
        McpServerConfig,
        ModelEndpoint,
        Project,
        PromptTemplate,
        Run,
    )

    statement = state.statement
    for model in (
        ModelEndpoint,
        ImageEndpoint,
        Project,
        PromptTemplate,
        KnowledgeBase,
        Document,
        McpServerConfig,
        AgentConfig,
        ChatSession,
        Run,
        Artifact,
    ):
        # Passing a concrete SQL expression avoids SQLAlchemy's lambda cache retaining the
        # previous request's tenant value when multiple clients share one application.
        statement = statement.options(with_loader_criteria(model, model.owner_id == owner_id, include_aliases=True))
    state.statement = statement


def engine() -> Engine:
    return _engine or configure_database()


def session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        configure_database()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    with session_factory()() as db:
        yield db


def create_schema() -> None:
    # Import registers all model tables with the declarative base.
    from . import models as _models  # noqa: F401

    Base.metadata.create_all(engine())


def initialize_tenancy(settings: Settings) -> str:
    """Create the bootstrap administrator and adopt all legacy rows atomically.

    SQLite cannot add a non-null foreign-key column in place. Legacy installations are upgraded
    with a nullable physical column, immediately backfilled, and protected by insert/update
    triggers. Fresh databases receive the declarative non-null schema directly.
    """

    owned_tables = (
        "model_endpoints",
        "image_endpoints",
        "prompt_templates",
        "knowledge_bases",
        "documents",
        "mcp_servers",
        "agents",
        "sessions",
        "runs",
        "artifacts",
    )
    db_engine = engine()
    with db_engine.begin() as connection:
        user = connection.execute(text("SELECT id FROM users ORDER BY created_at LIMIT 1")).first()
        if user is None:
            from .models import new_id

            owner_id = new_id()
            connection.execute(
                text(
                    "INSERT INTO users (id, username, phone, role, status, created_at, updated_at) "
                    "VALUES (:id, :username, NULL, 'admin', 'pending_claim', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": owner_id, "username": settings.auth_bootstrap_username},
            )
        else:
            owner_id = str(user[0])

        inspector = inspect(connection)
        column_migrations = {
            "agents": (
                ("review_policy", "VARCHAR(20) NOT NULL DEFAULT 'risk_based'"),
                ("review_model_endpoint_id", "VARCHAR(36)"),
                ("review_max_rounds", "INTEGER NOT NULL DEFAULT 2"),
                ("agent_type", "VARCHAR(30) NOT NULL DEFAULT 'general'"),
                ("builtin", "BOOLEAN NOT NULL DEFAULT 0"),
            ),
            "approvals": (("kind", "VARCHAR(30) NOT NULL DEFAULT 'tool_approval'"),),
            "knowledge_bases": (
                ("ocr_mode", "VARCHAR(20) NOT NULL DEFAULT 'auto'"),
                ("ocr_language", "VARCHAR(20) NOT NULL DEFAULT 'ch'"),
                ("ocr_min_chars", "INTEGER NOT NULL DEFAULT 30"),
            ),
            "documents": (
                ("extraction_method", "VARCHAR(20) NOT NULL DEFAULT 'text'"),
                ("ocr_pages", "JSON NOT NULL DEFAULT '[]'"),
                ("ocr_engine", "VARCHAR(80)"),
            ),
            "mcp_servers": (
                ("description", "TEXT NOT NULL DEFAULT ''"),
                ("source_url", "VARCHAR(1000)"),
                ("setup_hint", "TEXT NOT NULL DEFAULT ''"),
                ("builtin", "BOOLEAN NOT NULL DEFAULT 0"),
            ),
        }
        for table_name, additions in column_migrations.items():
            if table_name not in inspector.get_table_names():
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in additions:
                if column_name not in columns:
                    connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}'))
            inspector = inspect(connection)
        for table_name in owned_tables:
            if table_name not in inspector.get_table_names():
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "owner_id" not in columns:
                connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN owner_id VARCHAR(36)'))
            connection.execute(
                text(f'UPDATE "{table_name}" SET owner_id = :owner_id WHERE owner_id IS NULL'),
                {"owner_id": owner_id},
            )
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_owner_id" ON "{table_name}" (owner_id)')
            )
            connection.execute(
                text(
                    f'CREATE TRIGGER IF NOT EXISTS "trg_{table_name}_owner_insert" '
                    f'BEFORE INSERT ON "{table_name}" WHEN NEW.owner_id IS NULL '
                    "BEGIN SELECT RAISE(ABORT, 'owner_id is required'); END"
                )
            )
            connection.execute(
                text(
                    f'CREATE TRIGGER IF NOT EXISTS "trg_{table_name}_owner_update" '
                    f'BEFORE UPDATE OF owner_id ON "{table_name}" WHEN NEW.owner_id IS NULL '
                    "BEGIN SELECT RAISE(ABORT, 'owner_id is required'); END"
                )
            )
        # Every tenant receives a stable default project. Existing Agent/KB rows are adopted
        # without changing their owner or historical Run snapshots.
        from .models import new_id

        users = connection.execute(text("SELECT id FROM users")).all()
        default_projects: dict[str, str] = {}
        for (user_id_raw,) in users:
            user_id = str(user_id_raw)
            project = connection.execute(
                text("SELECT id FROM projects WHERE owner_id = :owner_id AND name = '默认项目' LIMIT 1"),
                {"owner_id": user_id},
            ).first()
            project_id = str(project[0]) if project else new_id()
            if project is None:
                connection.execute(
                    text(
                        "INSERT INTO projects (id, owner_id, name, description, status, created_at, updated_at) "
                        "VALUES (:id, :owner_id, '默认项目', '系统迁移与默认资源归属项目', 'active', "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"id": project_id, "owner_id": user_id},
                )
            default_projects[user_id] = project_id

        inspector = inspect(connection)
        for table_name in ("agents", "knowledge_bases"):
            if table_name not in inspector.get_table_names():
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "project_id" not in columns:
                connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN project_id VARCHAR(36)'))
            for user_id, project_id in default_projects.items():
                connection.execute(
                    text(
                        f'UPDATE "{table_name}" SET project_id = :project_id '
                        "WHERE owner_id = :owner_id AND project_id IS NULL"
                    ),
                    {"project_id": project_id, "owner_id": user_id},
                )
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_project_id" ON "{table_name}" (project_id)')
            )
            connection.execute(
                text(
                    f'CREATE TRIGGER IF NOT EXISTS "trg_{table_name}_project_insert" '
                    f'BEFORE INSERT ON "{table_name}" WHEN NEW.project_id IS NULL '
                    "BEGIN SELECT RAISE(ABORT, 'project_id is required'); END"
                )
            )
            connection.execute(
                text(
                    f'CREATE TRIGGER IF NOT EXISTS "trg_{table_name}_project_update" '
                    f'BEFORE UPDATE OF project_id ON "{table_name}" WHEN NEW.project_id IS NULL '
                    "BEGIN SELECT RAISE(ABORT, 'project_id is required'); END"
                )
            )
        # Sessions and Runs keep their own immutable project attribution. Otherwise moving an
        # Agent would rewrite the apparent ownership of all historical activity and reports.
        for table_name in ("sessions", "runs"):
            if table_name not in inspector.get_table_names():
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "project_id" not in columns:
                connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN project_id VARCHAR(36)'))
            if table_name == "sessions":
                connection.execute(
                    text(
                        'UPDATE "sessions" SET project_id = ('
                        "SELECT agents.project_id FROM agents WHERE agents.id = sessions.agent_id"
                        ") WHERE project_id IS NULL"
                    )
                )
            else:
                connection.execute(
                    text(
                        'UPDATE "runs" SET project_id = COALESCE(('
                        "SELECT sessions.project_id FROM sessions WHERE sessions.id = runs.session_id"
                        "), (SELECT agents.project_id FROM agents WHERE agents.id = runs.agent_id)) "
                        "WHERE project_id IS NULL"
                    )
                )
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_project_id" ON "{table_name}" (project_id)')
            )
            connection.execute(
                text(
                    f'CREATE TRIGGER IF NOT EXISTS "trg_{table_name}_project_insert" '
                    f'BEFORE INSERT ON "{table_name}" WHEN NEW.project_id IS NULL '
                    "BEGIN SELECT RAISE(ABORT, 'project_id is required'); END"
                )
            )
            connection.execute(
                text(
                    f'CREATE TRIGGER IF NOT EXISTS "trg_{table_name}_project_update" '
                    f'BEFORE UPDATE OF project_id ON "{table_name}" WHEN NEW.project_id IS NULL '
                    "BEGIN SELECT RAISE(ABORT, 'project_id is required'); END"
                )
            )
    return owner_id


def ensure_default_project(db: Session, owner_id: str) -> str:
    """Return a user's default project, creating it during first login if needed."""

    from sqlalchemy import select

    from .models import Project

    project = db.scalar(select(Project).where(Project.owner_id == owner_id, Project.name == "默认项目"))
    if project is None:
        project = Project(owner_id=owner_id, name="默认项目", description="系统默认资源归属项目")
        db.add(project)
        db.flush()
    return project.id


def ensure_builtin_prompt_templates(db: Session, owner_id: str) -> None:
    """Install immutable prompt baselines for every tenant, including newly registered users."""

    from sqlalchemy import select

    from .models import PromptTemplate

    templates = (
        (
            "通用可靠助手",
            "general",
            "适用于通用问答与任务协作，强调准确、透明和可验证。",
            "你是一个可靠、审慎的中文智能助理。先理解目标，再给出清晰可执行的答案；"
            "不确定时明确说明，不编造事实。使用外部资料或知识库时保留可核验来源。",
            ["通用", "可靠性"],
        ),
        (
            "知识库 RAG 助手",
            "rag",
            "严格依据知识库内容回答并提供文件、页码和块编号引用。",
            "你是企业知识库问答助手。优先依据检索上下文回答；每个关键结论必须给出文件名、"
            "页码（可取得时）和块编号。上下文不足时直接说明缺少证据，不得补造。",
            ["RAG", "引用"],
        ),
        (
            "深度研究助手",
            "research",
            "用于多来源调研、事实核验和结构化研究报告。",
            "你是深度研究助手。先拆解研究问题和证据标准，再收集多个独立来源，区分事实、"
            "推断与观点，标注时间范围和不确定性，最后输出结论、证据与待验证事项。",
            ["研究", "事实核验"],
        ),
        (
            "数据分析助手",
            "analysis",
            "用于数据质量检查、统计分析和可解释结论。",
            "你是数据分析助手。先检查字段、缺失值、异常值和统计口径，再开展分析。所有结论"
            "必须能追溯到计算结果；说明假设、限制与复现步骤，不夸大相关性或因果关系。",
            ["数据", "分析"],
        ),
        (
            "专业报告撰写",
            "writing",
            "将证据整理成结构清晰、可下载的专业报告。",
            "你是专业报告撰写助手。根据目标读者组织摘要、背景、发现、证据、建议和风险；"
            "保持术语一致、层级清晰，引用不得脱离原始证据。",
            ["报告", "写作"],
        ),
    )
    existing = set(
        db.scalars(select(PromptTemplate.name).where(PromptTemplate.owner_id == owner_id, PromptTemplate.builtin)).all()
    )
    for name, category, description, content, tags in templates:
        if name not in existing:
            db.add(
                PromptTemplate(
                    owner_id=owner_id,
                    name=name,
                    category=category,
                    description=description,
                    content=content,
                    tags=tags,
                    builtin=True,
                )
            )


def ensure_builtin_agents(db: Session, owner_id: str) -> AgentConfig:
    """Install the local deterministic digital-human designer for one tenant."""

    from sqlalchemy import select

    from .agent_config import revision_snapshot
    from .models import AgentConfig, AgentRevision

    agent = db.scalar(
        select(AgentConfig).where(
            AgentConfig.owner_id == owner_id,
            AgentConfig.agent_type == "digital_human",
            AgentConfig.builtin.is_(True),
        )
    )
    if agent is not None:
        return agent
    project_id = ensure_default_project(db, owner_id)
    names = set(db.scalars(select(AgentConfig.name).where(AgentConfig.owner_id == owner_id)).all())
    name = "数字人形象设计师"
    suffix = 1
    while name in names:
        suffix += 1
        name = f"数字人形象设计师（内置 {suffix}）"
    agent = AgentConfig(
        owner_id=owner_id,
        project_id=project_id,
        name=name,
        description="根据文字描述生成可动态展示、可导出的本地 2D 卡通数字人。",
        system_prompt=(
            "你是数字人形象设计师。将用户对人物外观、发型、服装、配饰和气质的描述转换为安全、"
            "简洁的卡通形象参数；不推断敏感身份属性，不复刻真实人物或受保护角色。"
        ),
        max_tool_loops=1,
        review_policy="off",
        agent_type="digital_human",
        builtin=True,
    )
    db.add(agent)
    db.flush()
    db.add(
        AgentRevision(
            agent_id=agent.id,
            version=1,
            snapshot=revision_snapshot(agent),
            reason="内置数字人智能体基线",
        )
    )
    return agent


def reset_database_state() -> None:
    """Dispose global state so tests can install a temporary database."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None

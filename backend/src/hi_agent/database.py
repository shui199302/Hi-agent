"""SQLAlchemy engine and transaction helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, ORMExecuteState, Session, sessionmaker, with_loader_criteria

from .config import Settings, get_settings


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
    connect_args = (
        {"check_same_thread": False, "timeout": 30}
        if settings.sqlite_url.startswith("sqlite")
        else {}
    )
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
    if not owner_id:
        return
    for item in session.new:
        if hasattr(item, "owner_id") and not getattr(item, "owner_id", None):
            item.owner_id = owner_id  # type: ignore[attr-defined]


@event.listens_for(Session, "do_orm_execute")
def _filter_owned_rows(state: ORMExecuteState) -> None:
    owner_id = state.session.info.get("owner_id")
    if not owner_id or not state.is_select or state.execution_options.get("skip_owner_filter"):
        return
    from .models import AgentConfig, ChatSession, Document, KnowledgeBase, McpServerConfig, ModelEndpoint, Run

    statement = state.statement
    for model in (ModelEndpoint, KnowledgeBase, Document, McpServerConfig, AgentConfig, ChatSession, Run):
        statement = statement.options(
            with_loader_criteria(model, lambda row: row.owner_id == owner_id, include_aliases=True)
        )
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

    owned_tables = ("model_endpoints", "knowledge_bases", "documents", "mcp_servers", "agents", "sessions", "runs")
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
    return owner_id


def reset_database_state() -> None:
    """Dispose global state so tests can install a temporary database."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None

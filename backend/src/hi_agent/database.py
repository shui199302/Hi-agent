"""SQLAlchemy engine and transaction helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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


def reset_database_state() -> None:
    """Dispose global state so tests can install a temporary database."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None

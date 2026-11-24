from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import get_settings


class _Clock:
    """Dev-only time travel (DEV_MODE): lets a demo jump a week ahead without waiting. Offset is zero in production."""
    offset = timedelta(0)


CLOCK = _Clock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc) + CLOCK.offset


class UTCDateTime(TypeDecorator):
    """Always store UTC, always return tz-aware UTC (SQLite drops tzinfo)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def make_engine(url: str):
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url == "sqlite://":
            from sqlalchemy.pool import StaticPool
            kw["poolclass"] = StaticPool
    return create_engine(url, **kw)


def init_db(url: str | None = None):
    global _engine, _Session
    _engine = make_engine(url or get_settings().database_url)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    from . import models  # noqa: F401
    Base.metadata.create_all(_engine)
    _add_missing_columns(_engine)
    if _engine.dialect.name == "postgresql":
        from .modules.geo import ensure_postgis
        ensure_postgis(_engine)
    return _engine


def get_engine():
    if _engine is None:
        init_db()
    return _engine


def SessionLocal():
    if _Session is None:
        init_db()
    return _Session()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns(engine) -> None:
    """Tiny forward-only migration: create_all() never alters existing tables, so columns added to a model later
    (e.g. jobs.urgent) are added here with their default. Use Alembic once the schema settles."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(dialect=engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                lit = "" if default is None else (" DEFAULT " + ("1" if default is True else "0" if default is False else repr(default)))
                if engine.dialect.name == "postgresql" and isinstance(default, bool):
                    lit = " DEFAULT " + ("TRUE" if default else "FALSE")
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}{lit}'))

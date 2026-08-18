from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import JSON, Engine, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


#: JSONB on Postgres, plain JSON on SQLite. Postgres is the real target, but
#: keeping the models renderable on SQLite is what lets the analytics and
#: ingest tests run in-process with no container.
JSONColumn = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    """Built on first use, not at import time.

    SQLAlchemy resolves the DBAPI driver when the engine is constructed, so an
    eager module-level engine would make importing any model require psycopg.
    The analytics tests run entirely on in-memory model instances and should
    not need a database driver, let alone a database.
    """
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def SessionLocal() -> Session:  # noqa: N802 — kept callable-as-factory
    return get_sessionmaker()()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

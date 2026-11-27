import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import Base

load_dotenv()
logger = logging.getLogger("fihcoin.database")

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")

    # Railway may provide postgres:// or postgresql:// URLs. SQLAlchemy's
    # async engine requires the asyncpg dialect.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


def get_engine():
    global _engine, _session_factory

    if _engine is None:
        _engine = create_async_engine(
            _database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _engine


async def initialize_database() -> None:
    """Verify PostgreSQL connectivity and create the initial schema if needed."""
    engine = get_engine()

    async with engine.begin() as connection:
        # The bot and API may boot at the same time. Serialize the initial
        # create_all operation so they cannot race to create the same tables.
        await connection.execute(text("SELECT pg_advisory_xact_lock(68421057)"))
        await connection.run_sync(Base.metadata.create_all)

    logger.info("PostgreSQL connection verified; database schema is ready.")


async def check_database_connection() -> bool:
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True



@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Provide a scoped async session; callers control transaction boundaries."""
    get_engine()
    if _session_factory is None:
        raise RuntimeError("Database session factory was not initialized.")

    async with _session_factory() as session:
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    get_engine()
    if _session_factory is None:
        raise RuntimeError("Database session factory was not initialized.")

    async with _session_factory() as session:
        yield session


async def close_database() -> None:
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _session_factory = None

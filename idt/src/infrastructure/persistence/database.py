"""Database connection and session management.

Provides async SQLAlchemy engine and session factory for MySQL.
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings
from src.infrastructure.logging.db_query_listener import DBQueryListener

# Module-level engine instance (lazy initialization)
_engine: AsyncEngine | None = None
_db_query_listener = DBQueryListener()


def get_engine() -> AsyncEngine:
    """Get or create the async database engine.

    Returns:
        AsyncEngine instance configured with the database URL from settings
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,          # SQLAlchemy 기본 출력 비활성 유지 (커스텀 리스너로 통일)
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _db_query_listener.register(_engine)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the async session factory.

    Returns:
        Callable that creates new AsyncSession instances
    """
    engine = get_engine()
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions.

    Yields:
        AsyncSession instance that is automatically closed after use
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()

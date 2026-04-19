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
    """Per-request AsyncSession with automatic commit/rollback (DB-001 §10.2).

    요청 1건 = AsyncSession 1개 = 트랜잭션 1건 원칙.

    - 정상 종료: `session.begin()` 블록 종료 시 자동 commit
    - 예외 전파: `session.begin()` 블록이 자동 rollback
    - 어느 경우든 `async with factory()` 가 세션을 close → 풀 반환

    Yields:
        AsyncSession 인스턴스 (요청 스코프, 자동 트랜잭션 경계)
    """
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session

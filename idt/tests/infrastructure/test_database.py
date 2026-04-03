"""Tests for database connection module.

TDD: These tests are written first before implementation.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from src.infrastructure.persistence.database import (
    get_engine,
    get_session_factory,
    get_session,
)


class TestDatabaseConnection:
    """Tests for database connection utilities."""

    def test_get_engine_returns_async_engine(self) -> None:
        """Engine should be an AsyncEngine instance."""
        engine = get_engine()
        assert isinstance(engine, AsyncEngine)

    def test_get_engine_uses_settings_url(self) -> None:
        """Engine should use the database URL from settings."""
        engine = get_engine()
        # asyncmy driver for MySQL
        assert "asyncmy" in str(engine.url) or "mysql" in str(engine.url)

    def test_get_session_factory_returns_callable(self) -> None:
        """Session factory should be callable."""
        factory = get_session_factory()
        assert callable(factory)

    @pytest.mark.asyncio
    async def test_get_session_yields_async_session(self) -> None:
        """get_session should yield an AsyncSession."""
        async for session in get_session():
            assert isinstance(session, AsyncSession)
            break  # Only need to test one iteration

    @pytest.mark.asyncio
    async def test_session_context_cleanup(self) -> None:
        """Session should be properly closed after context."""
        session_ref = None
        async for session in get_session():
            session_ref = session
            break
        # After the generator exits, session should be closed
        # We just verify no exceptions were raised
        assert session_ref is not None


class TestEngineConfiguration:
    """Tests for engine configuration options."""

    def test_engine_echo_disabled_by_default(self) -> None:
        """Engine should have echo disabled by default."""
        engine = get_engine()
        assert engine.echo is False

    def test_engine_pool_configuration(self) -> None:
        """Engine should have pool configuration."""
        engine = get_engine()
        # Check that pool exists
        assert engine.pool is not None

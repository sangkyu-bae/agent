"""Session lifecycle & transaction boundary tests (db-session-leak-fix).

DDD 원칙:
- "요청 1건 = AsyncSession 1개 = 트랜잭션 1건"
- 트랜잭션 경계(commit/rollback)는 `get_session` dependency 가 책임진다.
- Repository 는 commit/rollback 을 호출하지 않는다.

TDD (Red Phase): 구현 전에 실패를 확인해야 한다.
"""
from __future__ import annotations

import inspect
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.domain.auth.entities import UserRole, UserStatus
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import (
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.infrastructure.auth.models import RefreshTokenModel, UserModel
from src.infrastructure.auth.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.infrastructure.auth.user_repository import UserRepository
from src.infrastructure.persistence import database as db_module
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.persistence.repositories.conversation_repository import (
    SQLAlchemyConversationMessageRepository,
)
from src.infrastructure.persistence.repositories.conversation_summary_repository import (
    SQLAlchemyConversationSummaryRepository,
)


# ---------- helpers ----------


def _make_sqlite_url() -> tuple[str, str]:
    """Return (sqlite url, temp file path). File-based so separate connections see each other."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return f"sqlite+aiosqlite:///{tmp.name}", tmp.name


@pytest.fixture
async def sqlite_engine_and_factory():
    url, tmp_path = _make_sqlite_url()
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # auth 쪽 모델이 별도 Base 를 쓸 수 있으므로 함께 생성
    try:
        from src.infrastructure.auth.models import Base as AuthBase  # type: ignore

        async with engine.begin() as conn:
            await conn.run_sync(AuthBase.metadata.create_all)
    except Exception:
        pass

    factory = async_sessionmaker(engine, expire_on_commit=False)

    yield engine, factory, tmp_path

    await engine.dispose()
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


async def _read_all_messages(factory: async_sessionmaker[AsyncSession]) -> list:
    from sqlalchemy import select

    from src.infrastructure.persistence.models.conversation import (
        ConversationMessageModel,
    )

    async with factory() as session:
        result = await session.execute(select(ConversationMessageModel))
        return list(result.scalars().all())


async def _read_all_users(factory: async_sessionmaker[AsyncSession]) -> list:
    from sqlalchemy import select

    async with factory() as session:
        result = await session.execute(select(UserModel))
        return list(result.scalars().all())


async def _read_all_refresh_tokens(
    factory: async_sessionmaker[AsyncSession],
) -> list:
    from sqlalchemy import select

    async with factory() as session:
        result = await session.execute(select(RefreshTokenModel))
        return list(result.scalars().all())


def _make_message() -> ConversationMessage:
    return ConversationMessage(
        id=None,
        user_id=UserId("u"),
        session_id=SessionId("s"),
        role=MessageRole.USER,
        content="hello",
        turn_index=TurnIndex(1),
        created_at=datetime.now(),
    )


# ---------- TC-DB-1: get_session dependency transaction boundary ----------


class TestGetSessionTransactionBoundary:
    """`get_session` 이 `async with session.begin()` 으로 commit/rollback 을 강제해야 한다."""

    @pytest.mark.asyncio
    async def test_get_session_commits_on_success(
        self, monkeypatch, sqlite_engine_and_factory
    ):
        """정상 종료 시 dependency가 자동 commit → 별도 세션에서 행이 보인다."""
        _, factory, _ = sqlite_engine_and_factory
        monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)
        db_module._engine = None  # cache reset

        # get_session 을 async generator 로 소비하며 정상 종료
        gen = db_module.get_session()
        session = await gen.__anext__()
        repo = SQLAlchemyConversationMessageRepository(session)
        await repo.save(_make_message())
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

        # 별도 세션에서 행이 보여야 한다 (→ commit 되었다)
        rows = await _read_all_messages(factory)
        assert len(rows) == 1, (
            "get_session 이 정상 종료 시 자동 commit 하지 않음. "
            "`async with session.begin():` 필요."
        )

    @pytest.mark.asyncio
    async def test_get_session_rolls_back_on_exception(
        self, monkeypatch, sqlite_engine_and_factory
    ):
        """예외 전파 시 dependency가 자동 rollback → 별도 세션에서 행이 보이지 않는다."""
        _, factory, _ = sqlite_engine_and_factory
        monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)
        db_module._engine = None

        gen = db_module.get_session()
        session = await gen.__anext__()
        repo = SQLAlchemyConversationMessageRepository(session)
        await repo.save(_make_message())

        # generator 에 예외 주입 → rollback 되어야 한다
        with pytest.raises(RuntimeError):
            await gen.athrow(RuntimeError("boom"))

        rows = await _read_all_messages(factory)
        assert len(rows) == 0, (
            "get_session 이 예외 전파 시 rollback 하지 않음. "
            "`async with session.begin():` 필요."
        )


# ---------- TC-DB-2: Repository commit 금지 ----------


class TestRepositoryDoesNotCommit:
    """Repository 코드는 `session.commit()` / `session.rollback()` 을 호출하면 안 된다."""

    def test_conversation_message_repository_source_has_no_commit(self):
        src = inspect.getsource(SQLAlchemyConversationMessageRepository)
        assert "session.commit" not in src, (
            "SQLAlchemyConversationMessageRepository 에 session.commit() 호출 존재 "
            "(DB-001 §10.3 위반)"
        )
        assert "session.rollback" not in src

    def test_conversation_summary_repository_source_has_no_commit(self):
        src = inspect.getsource(SQLAlchemyConversationSummaryRepository)
        assert "session.commit" not in src
        assert "session.rollback" not in src

    def test_user_repository_source_has_no_commit(self):
        src = inspect.getsource(UserRepository)
        assert "session.commit" not in src, (
            "UserRepository 에 session.commit() 호출 존재 (DB-001 §10.3 위반)"
        )
        assert "session.rollback" not in src

    def test_refresh_token_repository_source_has_no_commit(self):
        src = inspect.getsource(RefreshTokenRepository)
        assert "session.commit" not in src, (
            "RefreshTokenRepository 에 session.commit() 호출 존재 (DB-001 §10.3 위반)"
        )
        assert "session.rollback" not in src


class TestRepositoryFlushWithoutCommit:
    """Repository.save 는 flush 만 하고 commit 하지 않는다 → 외부 세션에서는 보이지 않아야 한다."""

    @pytest.mark.asyncio
    async def test_message_save_is_not_committed_by_repo(
        self, sqlite_engine_and_factory
    ):
        _, factory, _ = sqlite_engine_and_factory

        session = factory()
        try:
            repo = SQLAlchemyConversationMessageRepository(session)
            await repo.save(_make_message())
            # 명시적 commit 을 하지 않는다
            # → 별도 세션에서 조회 시 아직 보이지 않아야 한다
            rows = await _read_all_messages(factory)
            assert rows == [], (
                "Repository.save 내부에서 commit 되고 있음. "
                "트랜잭션 경계는 dependency 가 책임져야 한다."
            )
        finally:
            await session.rollback()
            await session.close()

    @pytest.mark.asyncio
    async def test_user_save_is_not_committed_by_repo(
        self, sqlite_engine_and_factory
    ):
        _, factory, _ = sqlite_engine_and_factory

        from src.domain.auth.entities import User

        session = factory()
        logger = MagicMock()
        logger.info = MagicMock()
        logger.error = MagicMock()
        try:
            repo = UserRepository(session=session, logger=logger)
            user = User(
                id=None,
                email="u@example.com",
                password_hash="hash",
                role=UserRole.USER,
                status=UserStatus.PENDING,
                created_at=None,
                updated_at=None,
            )
            await repo.save(user)
            rows = await _read_all_users(factory)
            assert rows == [], (
                "UserRepository.save 내부에서 commit 되고 있음. "
                "트랜잭션 경계는 dependency 가 책임져야 한다."
            )
        finally:
            await session.rollback()
            await session.close()

    @pytest.mark.asyncio
    async def test_refresh_token_save_is_not_committed_by_repo(
        self, sqlite_engine_and_factory
    ):
        _, factory, _ = sqlite_engine_and_factory

        session = factory()
        logger = MagicMock()
        logger.info = MagicMock()
        logger.error = MagicMock()
        try:
            # user 를 먼저 만들어야 FK 성립
            from datetime import timedelta, timezone

            user_repo = UserRepository(session=session, logger=logger)
            from src.domain.auth.entities import User

            saved_user = await user_repo.save(
                User(
                    id=None,
                    email="rt@example.com",
                    password_hash="hash",
                    role=UserRole.USER,
                    status=UserStatus.PENDING,
                    created_at=None,
                    updated_at=None,
                )
            )
            rt_repo = RefreshTokenRepository(session=session, logger=logger)
            await rt_repo.save(
                user_id=saved_user.id,
                token_hash="t" * 32,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
            rows = await _read_all_refresh_tokens(factory)
            assert rows == [], (
                "RefreshTokenRepository.save 내부에서 commit 되고 있음. "
                "트랜잭션 경계는 dependency 가 책임져야 한다."
            )
        finally:
            await session.rollback()
            await session.close()


# ---------- TC-DB-3: UseCase 내 repository 는 같은 세션을 공유 (원자성) ----------


class TestSharedSessionAtomicity:
    """여러 repository 가 같은 세션을 공유하면 UseCase 예외 시 원자적으로 롤백된다."""

    @pytest.mark.asyncio
    async def test_shared_session_rolls_back_all_repos_on_exception(
        self, monkeypatch, sqlite_engine_and_factory
    ):
        """get_session 을 통해 session.begin() 경계에서 예외 발생 시
        동일 세션을 공유한 두 repository 의 쓰기는 모두 롤백되어야 한다."""
        _, factory, _ = sqlite_engine_and_factory
        monkeypatch.setattr(db_module, "get_session_factory", lambda: factory)
        db_module._engine = None

        from src.domain.conversation.entities import ConversationSummary

        gen = db_module.get_session()
        session = await gen.__anext__()
        msg_repo = SQLAlchemyConversationMessageRepository(session)
        sum_repo = SQLAlchemyConversationSummaryRepository(session)
        await msg_repo.save(_make_message())
        await sum_repo.save(
            ConversationSummary(
                id=None,
                user_id=UserId("u"),
                session_id=SessionId("s"),
                summary_content="s",
                start_turn=TurnIndex(1),
                end_turn=TurnIndex(3),
                created_at=datetime.now(),
            )
        )

        with pytest.raises(RuntimeError):
            await gen.athrow(RuntimeError("boom"))

        msgs = await _read_all_messages(factory)
        assert msgs == [], (
            "예외 발생 시 메시지 저장이 롤백되지 않음 (원자성 실패). "
            "get_session 의 session.begin() 블록이 rollback 을 책임져야 한다."
        )


# ---------- TC-DB-4: AutoBuild UseCase 는 세션을 보유하지 않는다 ----------


class TestAutoBuildUseCaseSignature:
    """lifespan singleton UseCase 는 DB session 을 가진 UC 를 생성자에서 받지 않는다.
    실행 시점(execute kwarg) 에 주입받아야 한다. (DB-001 §10.4)"""

    def test_auto_build_use_case_execute_accepts_create_agent_uc_kwarg(self):
        from src.application.auto_agent_builder.auto_build_use_case import (
            AutoBuildUseCase,
        )

        sig = inspect.signature(AutoBuildUseCase.execute)
        assert "create_agent_use_case" in sig.parameters, (
            "AutoBuildUseCase.execute 는 create_agent_use_case 를 실행 시점에 받아야 한다. "
            "lifespan 에서 세션 보유하는 CreateMiddlewareAgentUseCase 주입 금지."
        )

    def test_auto_build_use_case_init_does_not_take_create_agent_uc(self):
        from src.application.auto_agent_builder.auto_build_use_case import (
            AutoBuildUseCase,
        )

        sig = inspect.signature(AutoBuildUseCase.__init__)
        assert "create_agent_use_case" not in sig.parameters, (
            "AutoBuildUseCase.__init__ 가 create_agent_use_case 를 받고 있음 "
            "(lifespan singleton 이 세션을 영구 보유하게 된다)."
        )

    def test_auto_build_reply_use_case_init_does_not_take_create_agent_uc(self):
        from src.application.auto_agent_builder.auto_build_reply_use_case import (
            AutoBuildReplyUseCase,
        )

        sig = inspect.signature(AutoBuildReplyUseCase.__init__)
        assert "create_agent_use_case" not in sig.parameters, (
            "AutoBuildReplyUseCase.__init__ 가 create_agent_use_case 를 받고 있음."
        )

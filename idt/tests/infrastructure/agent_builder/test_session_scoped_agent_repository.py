"""SessionScopedAgentDefinitionRepository 단위 테스트.

Design Ref: subagent-context-scope FR-11 (module-4 실런 중 발견)

앱 싱글톤 WorkflowCompiler가 서브에이전트 정의를 런타임에 읽으려면 per-request
세션에 묶이지 않은 저장소가 필요하다. 매 호출마다 세션을 열어 기존
AgentDefinitionRepository에 위임한다 (SessionScopedLlmModelRepository 패턴).
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.infrastructure.agent_builder.session_scoped_agent_repository import (
    SessionScopedAgentDefinitionRepository,
)

_MODULE = "src.infrastructure.agent_builder.session_scoped_agent_repository"


class _FakeSession:
    def __init__(self) -> None:
        self.begun = 0

    @asynccontextmanager
    async def _begin(self):
        self.begun += 1
        yield

    def begin(self):
        return self._begin()


def _factory():
    sessions: list[_FakeSession] = []

    @asynccontextmanager
    async def _open():
        session = _FakeSession()
        sessions.append(session)
        yield session

    return MagicMock(side_effect=_open), sessions


@pytest.fixture
def inner():
    repo = MagicMock()
    for name in (
        "save", "find_by_id", "find_by_id_with_status", "update", "list_by_user",
        "list_accessible", "soft_delete", "count_forks", "count_subscribers",
    ):
        setattr(repo, name, AsyncMock(return_value=f"{name}-result"))
    return repo


def test_인터페이스를_구현한다():
    factory, _ = _factory()
    adapter = SessionScopedAgentDefinitionRepository(factory, MagicMock())
    assert isinstance(adapter, AgentDefinitionRepositoryInterface)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args", [
    ("find_by_id", ("a1", "r")),
    ("find_by_id_with_status", ("a1", "r")),
    ("list_by_user", ("u1", "r")),
    ("list_accessible", ("u1", ["d1"], "all", None, 1, 20, "r")),
    ("count_forks", ("a1", "r")),
    ("count_subscribers", ("a1", "r")),
])
async def test_조회는_호출마다_새_세션으로_위임_트랜잭션_없음(inner, method, args):
    factory, sessions = _factory()
    logger = MagicMock()
    with patch(f"{_MODULE}.AgentDefinitionRepository", return_value=inner) as cls:
        adapter = SessionScopedAgentDefinitionRepository(factory, logger)
        assert await getattr(adapter, method)(*args) == f"{method}-result"
        await getattr(adapter, method)(*args)

    assert len(sessions) == 2  # 호출마다 새 세션
    assert all(s.begun == 0 for s in sessions)
    cls.assert_called_with(sessions[-1], logger)
    getattr(inner, method).assert_awaited_with(*args)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args,expected", [
    ("save", ("agent", "r"), "save-result"),
    ("update", ("agent", "r"), "update-result"),
    ("soft_delete", ("a1", "r"), None),  # 인터페이스상 반환 없음
])
async def test_쓰기는_자체_트랜잭션으로_완결(inner, method, args, expected):
    factory, sessions = _factory()
    with patch(f"{_MODULE}.AgentDefinitionRepository", return_value=inner):
        adapter = SessionScopedAgentDefinitionRepository(factory, MagicMock())
        assert await getattr(adapter, method)(*args) == expected

    assert sessions[0].begun == 1
    getattr(inner, method).assert_awaited_once_with(*args)

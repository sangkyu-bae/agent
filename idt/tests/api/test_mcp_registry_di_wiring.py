"""MCP Registry DI 배선 테스트 — sync UseCase 주입과 세션 공유.

Design Ref: mcp-tool-auto-sync §11.4 / DB-001
"요청 1건 = AsyncSession 1개"를 지키는지, 즉 등록 UseCase와 sync UseCase가
**같은 세션 인스턴스**를 공유하는지 구조적으로 고정한다.
repository 인스턴스가 2개인 것은 무방하고, 금지되는 것은 세션이 2개인 경우다.
"""
from unittest.mock import MagicMock

import pytest

from src.api.main import create_mcp_registry_factories


@pytest.fixture
def factories():
    register_f, _list_f, update_f, _delete_f, _test_f = create_mcp_registry_factories()
    return register_f, update_f


def _sessions_of(use_case) -> set[int]:
    """UseCase가 들고 있는 repository들의 세션 객체 id 집합."""
    sessions: set[int] = set()

    def _collect(obj, depth=0):
        if depth > 3 or obj is None:
            return
        for attr in vars(obj).values():
            session = getattr(attr, "_session", None)
            if session is not None:
                sessions.add(id(session))
            elif hasattr(attr, "__dict__") and not isinstance(attr, (str, bytes)):
                _collect(attr, depth + 1)

    _collect(use_case)
    return sessions


class TestRegisterFactoryWiring:
    def test_sync_use_case_is_injected(self, factories):
        """FR-01: 등록 UseCase에 SyncMcpToolsUseCase가 주입된다."""
        register_f, _ = factories
        uc = register_f(session=MagicMock())

        assert uc._sync_use_case is not None

    def test_sync_timeout_comes_from_config(self, factories):
        """config 하드코딩 금지 — settings에서 온 값이어야 한다."""
        from src.config import settings

        register_f, _ = factories
        uc = register_f(session=MagicMock())

        assert uc._sync_timeout_sec == settings.mcp_tool_sync_timeout_sec

    def test_all_repositories_share_one_session(self, factories):
        """DB-001: 등록 repo와 sync UseCase 내부 repo가 동일 세션을 쓴다."""
        register_f, _ = factories
        session = MagicMock()
        uc = register_f(session=session)

        assert _sessions_of(uc) == {id(session)}


class TestUpdateFactoryWiring:
    def test_sync_use_case_is_injected(self, factories):
        """FR-02: 수정 UseCase에도 주입된다."""
        _, update_f = factories
        uc = update_f(session=MagicMock())

        assert uc._sync_use_case is not None

    def test_all_repositories_share_one_session(self, factories):
        _, update_f = factories
        session = MagicMock()
        uc = update_f(session=session)

        assert _sessions_of(uc) == {id(session)}

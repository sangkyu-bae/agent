"""AgentMiddlewareRepository.upsert_config 단위 테스트 (approval-gate Check G3)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.middleware.repository import AgentMiddlewareRepository


def _repo(existing=None, count=0):
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    first = MagicMock()
    first.scalar_one_or_none.return_value = existing
    second = MagicMock()
    second.scalar.return_value = count
    session.execute = AsyncMock(side_effect=[first, second])
    return AgentMiddlewareRepository(session=session, logger=MagicMock()), session


class TestUpsertConfig:
    @pytest.mark.asyncio
    async def test_행이_있으면_config만_갱신한다(self):
        existing = MagicMock(config=None)
        repo, session = _repo(existing=existing)
        await repo.upsert_config(
            agent_id="ag1", middleware_type="approval_gate",
            config={"execute_after": "0 0 * * *"}, request_id="r",
        )
        assert existing.config == {"execute_after": "0 0 * * *"}
        session.add.assert_not_called()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_행이_없으면_적용_행을_만든다(self):
        """행 존재 = 적용 (builtin-middleware 규약)."""
        repo, session = _repo(existing=None, count=2)
        await repo.upsert_config(
            agent_id="ag1", middleware_type="approval_gate",
            config={"mode": "always"}, request_id="r",
        )
        model = session.add.call_args.args[0]
        assert model.middleware_type == "approval_gate"
        assert model.config == {"mode": "always"}
        assert model.sort_order == 2

    @pytest.mark.asyncio
    async def test_commit하지_않는다(self):
        """DB-001 — 트랜잭션 경계는 호출측."""
        repo, session = _repo(existing=None)
        await repo.upsert_config(
            agent_id="ag1", middleware_type="approval_gate",
            config={}, request_id="r",
        )
        assert not session.commit.called

    @pytest.mark.asyncio
    async def test_입력_dict를_복사해_저장한다(self):
        """호출측이 나중에 dict 를 바꿔도 저장값이 오염되지 않는다."""
        existing = MagicMock(config=None)
        repo, _ = _repo(existing=existing)
        cfg = {"mode": "always"}
        await repo.upsert_config(
            agent_id="ag1", middleware_type="approval_gate",
            config=cfg, request_id="r",
        )
        cfg["mode"] = "off"
        assert existing.config == {"mode": "always"}


class TestAllImplementationsInstantiable:
    """인터페이스에 추상 메서드를 추가하면 모든 구현체가 따라와야 한다.

    Check G3 수정 중 upsert_config 를 추가하자 SessionScoped 어댑터가
    추상 클래스가 되어 **앱 기동 자체가 실패**했다. 그 회귀를 고정한다.
    """

    def test_세션스코프_어댑터가_인스턴스화된다(self):
        from src.infrastructure.middleware.session_scoped import (
            SessionScopedAgentMiddlewareRepository,
        )

        SessionScopedAgentMiddlewareRepository(MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_세션스코프_어댑터는_쓰기를_거부한다(self):
        """읽기 전용 규약 — 호출측 트랜잭션에 참여하지 못한다."""
        from src.infrastructure.middleware.session_scoped import (
            SessionScopedAgentMiddlewareRepository,
        )

        repo = SessionScopedAgentMiddlewareRepository(MagicMock(), MagicMock())
        with pytest.raises(NotImplementedError):
            await repo.upsert_config(
                agent_id="a", middleware_type="approval_gate",
                config={}, request_id="r",
            )

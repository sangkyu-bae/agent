"""ListApprovalsUseCase 단위 테스트.

Design Ref: §4.1 (목록), §5.5 (벨 배지), §8.2 L1 #1.
소유 에이전트 해석이 리포지토리가 아니라 여기 있는 이유는 module-1 에서
측정된 문제 때문이다 — 리포지토리가 agent_definition ORM 을 참조하면 공유
Base.metadata 가 오염돼 sqlite 통합 테스트 91건이 무너졌다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.approval.list_use_case import (
    DEFAULT_STATUSES,
    ListApprovalsUseCase,
)


def _uc(*, agent_ids=("ag1", "ag2"), items=None, total=0, unseen=0):
    repo = MagicMock()
    repo.list_for_user = AsyncMock(return_value=(items or [], total))
    repo.count_unseen = AsyncMock(return_value=unseen)
    repo.mark_seen = AsyncMock()

    agent_repo = MagicMock()
    agents = []
    for i in agent_ids:
        a = MagicMock(id=i)
        a.name = f"에이전트-{i}"
        agents.append(a)
    agent_repo.list_by_user = AsyncMock(return_value=agents)
    return ListApprovalsUseCase(
        approval_repo=repo, agent_repo=agent_repo, logger=MagicMock()
    ), repo, agent_repo


class TestList:
    @pytest.mark.asyncio
    async def test_소유_에이전트_id로_범위를_좁힌다(self):
        uc, repo, _ = _uc()
        await uc.list(user_id="u1", request_id="req1")
        assert repo.list_for_user.await_args.args[0] == ("ag1", "ag2")

    @pytest.mark.asyncio
    async def test_소유_에이전트가_없으면_조회하지_않는다(self):
        """빈 IN 절로 DB 를 때리지 않는다."""
        uc, repo, _ = _uc(agent_ids=())
        page = await uc.list(user_id="u1", request_id="req1")
        assert (page.items, page.total) == ([], 0)
        repo.list_for_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_기본_상태는_pending과_scheduled(self):
        """executed·rejected 는 기본 목록에서 빠진다 — 할 일만 보인다."""
        uc, repo, _ = _uc()
        await uc.list(user_id="u1", request_id="req1")
        assert repo.list_for_user.await_args.kwargs["statuses"] == DEFAULT_STATUSES
        assert DEFAULT_STATUSES == ("pending", "scheduled")

    @pytest.mark.asyncio
    async def test_상태를_명시하면_그대로_넘긴다(self):
        uc, repo, _ = _uc()
        await uc.list(user_id="u1", request_id="req1", statuses=("executed",))
        assert repo.list_for_user.await_args.kwargs["statuses"] == ("executed",)

    @pytest.mark.asyncio
    async def test_페이지가_offset으로_환산된다(self):
        uc, repo, _ = _uc()
        await uc.list(user_id="u1", request_id="req1", page=3, size=20)
        assert repo.list_for_user.await_args.kwargs["offset"] == 40
        assert repo.list_for_user.await_args.kwargs["limit"] == 20

    @pytest.mark.asyncio
    async def test_page가_0이하여도_offset은_음수가_아니다(self):
        uc, repo, _ = _uc()
        await uc.list(user_id="u1", request_id="req1", page=0)
        assert repo.list_for_user.await_args.kwargs["offset"] == 0

    @pytest.mark.asyncio
    async def test_총계를_그대로_돌려준다(self):
        uc, _, _ = _uc(items=[MagicMock()], total=37)
        page = await uc.list(user_id="u1", request_id="req1")
        assert page.total == 37


class TestCountUnseen:
    @pytest.mark.asyncio
    async def test_미확인_건수를_돌려준다(self):
        uc, _, _ = _uc(unseen=3)
        assert await uc.count_unseen(user_id="u1", request_id="req1") == 3

    @pytest.mark.asyncio
    async def test_소유_에이전트가_없으면_0(self):
        uc, repo, _ = _uc(agent_ids=())
        assert await uc.count_unseen(user_id="u1", request_id="req1") == 0
        repo.count_unseen.assert_not_awaited()


class TestMarkSeen:
    """Check G7 — 이전에는 user_id 를 받기만 하고 쓰지 않아, 아무 사용자나
    타인의 approval_id 를 확인 처리(벨 배지 해제)할 수 있었다."""

    @pytest.mark.asyncio
    async def test_소유_에이전트_범위로_제한한다(self):
        uc, repo, _ = _uc(agent_ids=("ag1", "ag2"))
        await uc.mark_seen("ap1", user_id="u1", request_id="req1")
        repo.mark_seen.assert_awaited_once_with("ap1", ("ag1", "ag2"), "req1")

    @pytest.mark.asyncio
    async def test_소유_에이전트가_없으면_아무것도_하지_않는다(self):
        uc, repo, _ = _uc(agent_ids=())
        await uc.mark_seen("ap1", user_id="u1", request_id="req1")
        repo.mark_seen.assert_not_awaited()



class TestAgentNames:
    @pytest.mark.asyncio
    async def test_소유_에이전트_이름_맵을_돌려준다(self):
        """Check G6 — 이미 조회한 소유 에이전트 목록에서 이름을 매핑한다(추가 쿼리 없음)."""
        uc, _, agent_repo = _uc(agent_ids=("ag1", "ag2"))
        page = await uc.list(user_id="u1", request_id="req1")
        assert page.agent_names == {"ag1": "에이전트-ag1", "ag2": "에이전트-ag2"}
        agent_repo.list_by_user.assert_awaited_once()

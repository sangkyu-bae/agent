"""MemoryCrudUseCase 단위 테스트 (agent-memory Design §3-3).

결정 ②: 타인 소유·미존재 모두 "찾을 수 없습니다" ValueError — 라우터에서 404 은닉.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.memory.crud_use_case import MemoryCrudUseCase
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType


def _memory(memory_id=1, user_id="u1", mem_type=MemoryType.PROFILE, content="여신 심사팀") -> Memory:
    return Memory(
        id=memory_id, scope=MemoryScope.USER, user_id=user_id, tier=0,
        mem_type=mem_type, content=content,
    )


def _make(count=0, found=None):
    repo = MagicMock()
    repo.save = AsyncMock(side_effect=lambda m, request_id: m)
    repo.count_active_by_user = AsyncMock(return_value=count)
    repo.find_active_by_user = AsyncMock(return_value=[])
    repo.find_by_id = AsyncMock(return_value=found)
    repo.update = AsyncMock(side_effect=lambda m, request_id: m)
    repo.delete = AsyncMock(return_value=True)
    uc = MemoryCrudUseCase(memory_repo=repo, logger=MagicMock(), max_active_per_user=30)
    return uc, repo


class TestCreate:
    async def test_정상_생성은_phase1_기본값(self):
        uc, repo = _make(count=0)

        created = await uc.create("u1", "profile", "여신 심사팀 소속", "req-1")

        assert created.scope == MemoryScope.USER
        assert created.user_id == "u1"
        assert created.tier == 0
        assert created.mem_type == MemoryType.PROFILE
        assert created.status == MemoryStatus.ACTIVE
        assert created.confidence == 100
        repo.save.assert_awaited_once()

    async def test_상한_도달_시_거부(self):
        uc, _ = _make(count=30)
        with pytest.raises(ValueError, match="상한"):
            await uc.create("u1", "profile", "내용", "req-1")

    async def test_길이_초과_거부(self):
        uc, _ = _make(count=0)
        with pytest.raises(ValueError):
            await uc.create("u1", "profile", "가" * 501, "req-1")

    async def test_잘못된_타입_거부(self):
        uc, _ = _make(count=0)
        with pytest.raises(ValueError):
            await uc.create("u1", "unknown_type", "내용", "req-1")


class TestListActive:
    async def test_본인_user_id로_조회(self):
        uc, repo = _make()
        await uc.list_active("u1", "req-1")
        repo.find_active_by_user.assert_awaited_once_with("u1", "req-1")


class TestUpdate:
    async def test_본인_소유_수정_성공(self):
        uc, repo = _make(found=_memory(user_id="u1"))

        updated = await uc.update("u1", 1, "domain_term", "'한도'는 동일인 여신한도", "req-1")

        assert updated.mem_type == MemoryType.DOMAIN_TERM
        assert updated.content == "'한도'는 동일인 여신한도"
        repo.update.assert_awaited_once()

    async def test_부분_수정_content만(self):
        uc, repo = _make(found=_memory(user_id="u1", mem_type=MemoryType.PREFERENCE))

        updated = await uc.update("u1", 1, None, "새 내용", "req-1")

        assert updated.mem_type == MemoryType.PREFERENCE
        assert updated.content == "새 내용"

    async def test_타인_소유는_찾을_수_없음(self):
        uc, _ = _make(found=_memory(user_id="other"))
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.update("u1", 1, None, "내용", "req-1")

    async def test_미존재는_찾을_수_없음(self):
        uc, _ = _make(found=None)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.update("u1", 999, None, "내용", "req-1")

    async def test_수정_내용_길이_검증(self):
        uc, _ = _make(found=_memory(user_id="u1"))
        with pytest.raises(ValueError):
            await uc.update("u1", 1, None, "가" * 501, "req-1")


class TestDelete:
    async def test_본인_소유_삭제_성공(self):
        uc, repo = _make(found=_memory(user_id="u1"))
        await uc.delete("u1", 1, "req-1")
        repo.delete.assert_awaited_once_with(1, "req-1")

    async def test_타인_소유_삭제는_찾을_수_없음(self):
        uc, repo = _make(found=_memory(user_id="other"))
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.delete("u1", 1, "req-1")
        repo.delete.assert_not_awaited()

    async def test_미존재_삭제는_찾을_수_없음(self):
        uc, _ = _make(found=None)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.delete("u1", 999, "req-1")

"""MemoryCrudUseCase 단위 테스트 (agent-memory Design §3-3).

결정 ②: 타인 소유·미존재 모두 "찾을 수 없습니다" ValueError — 라우터에서 404 은닉.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.memory.crud_use_case import MemoryCrudUseCase
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType


def _memory(
    memory_id=1, user_id="u1", mem_type=MemoryType.PROFILE,
    content="여신 심사팀", status=MemoryStatus.ACTIVE,
) -> Memory:
    return Memory(
        id=memory_id, scope=MemoryScope.USER, user_id=user_id, tier=0,
        mem_type=mem_type, content=content, status=status,
    )


def _make(count=0, found=None, org_count=0, org_existing=None):
    repo = MagicMock()
    repo.save = AsyncMock(side_effect=lambda m, request_id: m)
    repo.count_active_by_user = AsyncMock(return_value=count)
    repo.find_active_by_user = AsyncMock(return_value=[])
    repo.find_by_user_and_status = AsyncMock(return_value=[])
    repo.find_by_id = AsyncMock(return_value=found)
    repo.update = AsyncMock(side_effect=lambda m, request_id: m)
    repo.delete = AsyncMock(return_value=True)
    repo.find_active_by_departments = AsyncMock(return_value=org_existing or [])
    repo.count_active_by_department = AsyncMock(return_value=org_count)
    uc = MemoryCrudUseCase(
        memory_repo=repo, logger=MagicMock(),
        max_active_per_user=30, max_pending_per_user=20,
        max_active_per_department=50,
    )
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


class TestApproveReject:
    async def test_pending_승인은_ACTIVE_전이(self):
        uc, repo = _make(count=0, found=_memory(status=MemoryStatus.PENDING))

        approved = await uc.approve("u1", 1, "req-1")

        assert approved.status == MemoryStatus.ACTIVE
        repo.update.assert_awaited_once()

    async def test_승인_시_active_상한_검증(self):
        uc, _ = _make(count=30, found=_memory(status=MemoryStatus.PENDING))
        with pytest.raises(ValueError, match="상한"):
            await uc.approve("u1", 1, "req-1")

    async def test_비pending_승인은_422_경로(self):
        uc, _ = _make(found=_memory(status=MemoryStatus.ACTIVE))
        with pytest.raises(ValueError, match="승인 대기"):
            await uc.approve("u1", 1, "req-1")

    async def test_타인_소유_승인은_404_은닉(self):
        uc, _ = _make(found=_memory(user_id="other", status=MemoryStatus.PENDING))
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.approve("u1", 1, "req-1")

    async def test_pending_거부는_REJECTED_전이(self):
        uc, repo = _make(found=_memory(status=MemoryStatus.PENDING))

        rejected = await uc.reject("u1", 1, "req-1")

        assert rejected.status == MemoryStatus.REJECTED
        repo.update.assert_awaited_once()

    async def test_비pending_거부는_422_경로(self):
        uc, _ = _make(found=_memory(status=MemoryStatus.REJECTED))
        with pytest.raises(ValueError, match="승인 대기"):
            await uc.reject("u1", 1, "req-1")


class TestListByStatus:
    async def test_상태별_목록_조회(self):
        uc, repo = _make()
        await uc.list_by_status("u1", MemoryStatus.PENDING, "req-1")
        repo.find_by_user_and_status.assert_awaited_once_with(
            "u1", MemoryStatus.PENDING, "req-1"
        )

    async def test_pending_cap_노출(self):
        uc, _ = _make()
        assert uc.max_pending_per_user == 20


class TestOrgScope:
    async def test_부서_메모리_작성(self):
        uc, repo = _make(org_count=0)

        created = await uc.create_org("d1", "domain_term", "부서 용어", "req-1")

        assert created.scope == MemoryScope.ORG
        assert created.user_id == "d1"
        assert created.mem_type == MemoryType.DOMAIN_TERM
        repo.save.assert_awaited_once()

    async def test_부서_상한_초과_거부(self):
        uc, _ = _make(org_count=50)
        with pytest.raises(ValueError, match="상한"):
            await uc.create_org("d1", "domain_term", "내용", "req-1")

    async def test_list_org(self):
        uc, repo = _make()
        await uc.list_org(["d1", "d2"], "req-1")
        repo.find_active_by_departments.assert_awaited_once_with(["d1", "d2"], "req-1")

    async def test_승격은_org_복사_원본유지(self):
        uc, repo = _make(found=_memory(user_id="u1", content="승격 대상"))

        promoted = await uc.promote("u1", 1, "d1", "req-1")

        assert promoted.scope == MemoryScope.ORG
        assert promoted.user_id == "d1"
        assert promoted.content == "승격 대상"
        repo.save.assert_awaited_once()  # 신규 org 저장
        repo.delete.assert_not_awaited()  # 원본 유지

    async def test_승격_부서_중복은_거부(self):
        uc, _ = _make(
            found=_memory(user_id="u1", content="중복 내용"),
            org_existing=[_memory(user_id="d1", content="중복 내용")],
        )
        with pytest.raises(ValueError, match="이미 부서"):
            await uc.promote("u1", 1, "d1", "req-1")

    async def test_승격_타인_메모리는_찾을_수_없음(self):
        uc, _ = _make(found=_memory(user_id="other", content="x"))
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.promote("u1", 1, "d1", "req-1")


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

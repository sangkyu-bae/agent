"""Application 테스트: skill_builder UseCase 6종."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.skill_builder.create_skill_use_case import CreateSkillUseCase
from src.application.skill_builder.delete_skill_use_case import DeleteSkillUseCase
from src.application.skill_builder.fork_skill_use_case import ForkSkillUseCase
from src.application.skill_builder.get_skill_use_case import GetSkillUseCase
from src.application.skill_builder.list_skills_use_case import ListSkillsUseCase
from src.application.skill_builder.schemas import (
    CreateSkillRequest,
    ListSkillsRequest,
    UpdateSkillRequest,
)
from src.application.skill_builder.update_skill_use_case import UpdateSkillUseCase
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)


def _skill(**overrides) -> SkillDefinition:
    base = dict(
        id="skill-1",
        user_id="1",
        name="환율 계산기",
        description="설명",
        instruction="지시문",
        trigger="환율",
        script_type=SkillScriptType.PYTHON,
        script_content="print(1)",
        status="active",
        visibility=SkillVisibility.PRIVATE,
        department_id=None,
        forked_from=None,
        forked_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    base.update(overrides)
    return SkillDefinition(**base)


def _dept_repo(dept_ids=None):
    repo = MagicMock()
    rows = [MagicMock(department_id=d) for d in (dept_ids or [])]
    repo.find_departments_by_user = AsyncMock(return_value=rows)
    return repo


# ── Create ──────────────────────────────────────────────────────

class TestCreateSkillUseCase:
    @pytest.mark.asyncio
    async def test_creates_and_returns_response(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.save.side_effect = lambda s, r: s
        uc = CreateSkillUseCase(repository=repo, logger=MagicMock())
        req = CreateSkillRequest(
            user_id="1", name="환율", description="d",
            instruction="이렇게 하라", script_type="python",
            script_content="print(1)", visibility="private",
        )
        result = await uc.execute(req, "req-1")
        assert result.name == "환율"
        assert result.visibility == "private"
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_instruction_raises(self):
        uc = CreateSkillUseCase(repository=AsyncMock(), logger=MagicMock())
        req = CreateSkillRequest(user_id="1", name="n", instruction="  ")
        with pytest.raises(ValueError, match="instruction"):
            await uc.execute(req, "req-1")

    @pytest.mark.asyncio
    async def test_none_type_with_script_raises(self):
        uc = CreateSkillUseCase(repository=AsyncMock(), logger=MagicMock())
        req = CreateSkillRequest(
            user_id="1", name="n", instruction="i",
            script_type="none", script_content="print(1)",
        )
        with pytest.raises(ValueError, match="none"):
            await uc.execute(req, "req-1")

    @pytest.mark.asyncio
    async def test_department_without_dept_id_raises(self):
        uc = CreateSkillUseCase(repository=AsyncMock(), logger=MagicMock())
        req = CreateSkillRequest(
            user_id="1", name="n", instruction="i", visibility="department",
        )
        with pytest.raises(ValueError, match="department"):
            await uc.execute(req, "req-1")


# ── Get ─────────────────────────────────────────────────────────

class TestGetSkillUseCase:
    @pytest.mark.asyncio
    async def test_owner_gets_private(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="1")
        uc = GetSkillUseCase(repository=repo, logger=MagicMock())
        result = await uc.execute("skill-1", "req-1", viewer_user_id="1", viewer_role="user")
        assert result.id == "skill-1"

    @pytest.mark.asyncio
    async def test_missing_returns_none(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = None
        uc = GetSkillUseCase(repository=repo, logger=MagicMock())
        result = await uc.execute("x", "req-1", viewer_user_id="1", viewer_role="user")
        assert result is None

    @pytest.mark.asyncio
    async def test_other_user_private_raises_permission(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="2")
        uc = GetSkillUseCase(repository=repo, logger=MagicMock())
        with pytest.raises(PermissionError):
            await uc.execute("skill-1", "req-1", viewer_user_id="1", viewer_role="user")


# ── Update ──────────────────────────────────────────────────────

class TestUpdateSkillUseCase:
    @pytest.mark.asyncio
    async def test_owner_updates_name(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="1")
        repo.update.side_effect = lambda s, r: s
        uc = UpdateSkillUseCase(repository=repo, logger=MagicMock())
        req = UpdateSkillRequest(name="새 이름")
        result = await uc.execute("skill-1", req, "req-1", viewer_user_id="1")
        assert result.name == "새 이름"

    @pytest.mark.asyncio
    async def test_non_owner_raises_permission(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="2")
        uc = UpdateSkillUseCase(repository=repo, logger=MagicMock())
        with pytest.raises(PermissionError):
            await uc.execute("skill-1", UpdateSkillRequest(name="x"), "req-1", viewer_user_id="1")

    @pytest.mark.asyncio
    async def test_missing_raises_value_error(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = None
        uc = UpdateSkillUseCase(repository=repo, logger=MagicMock())
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("x", UpdateSkillRequest(name="x"), "req-1", viewer_user_id="1")


# ── Delete ──────────────────────────────────────────────────────

class TestDeleteSkillUseCase:
    @pytest.mark.asyncio
    async def test_owner_soft_deletes(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="1")
        uc = DeleteSkillUseCase(repository=repo, logger=MagicMock())
        await uc.execute("skill-1", viewer_user_id="1", viewer_role="user", request_id="req-1")
        repo.soft_delete.assert_called_once_with("skill-1", "req-1")

    @pytest.mark.asyncio
    async def test_admin_can_delete_others(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="2")
        uc = DeleteSkillUseCase(repository=repo, logger=MagicMock())
        await uc.execute("skill-1", viewer_user_id="1", viewer_role="admin", request_id="req-1")
        repo.soft_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_owner_raises_permission(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="2")
        uc = DeleteSkillUseCase(repository=repo, logger=MagicMock())
        with pytest.raises(PermissionError):
            await uc.execute("skill-1", viewer_user_id="1", viewer_role="user", request_id="req-1")


# ── List ────────────────────────────────────────────────────────

class TestListSkillsUseCase:
    @pytest.mark.asyncio
    async def test_my_returns_owned(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.list_by_user.return_value = [_skill(user_id="1")]
        uc = ListSkillsUseCase(repository=repo, dept_repo=_dept_repo(), logger=MagicMock())
        result = await uc.execute_my("1", "user", "req-1")
        assert result.total == 1
        assert result.skills[0].can_edit is True

    @pytest.mark.asyncio
    async def test_accessible_uses_dept_ids(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.list_accessible.return_value = ([_skill(user_id="2", visibility=SkillVisibility.PUBLIC)], 1)
        dept = _dept_repo(["d1"])
        uc = ListSkillsUseCase(repository=repo, dept_repo=dept, logger=MagicMock())
        req = ListSkillsRequest(scope="all", page=1, size=20)
        result = await uc.execute_accessible("1", "user", req, "req-1")
        assert result.total == 1
        _, kwargs = repo.list_accessible.call_args
        assert kwargs["viewer_department_ids"] == ["d1"]


# ── Fork ────────────────────────────────────────────────────────

class TestForkSkillUseCase:
    @pytest.mark.asyncio
    async def test_fork_public_skill(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="2", visibility=SkillVisibility.PUBLIC)
        repo.save.side_effect = lambda s, r: s
        uc = ForkSkillUseCase(repository=repo, dept_repo=_dept_repo(), logger=MagicMock())
        result = await uc.execute("skill-1", user_id="1", custom_name=None, request_id="req-1")
        assert result.user_id == "1"
        assert result.forked_from == "skill-1"
        assert result.visibility == "private"

    @pytest.mark.asyncio
    async def test_fork_own_skill_raises(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="1")
        uc = ForkSkillUseCase(repository=repo, dept_repo=_dept_repo(), logger=MagicMock())
        with pytest.raises(ValueError, match="자신의"):
            await uc.execute("skill-1", user_id="1", custom_name=None, request_id="req-1")

    @pytest.mark.asyncio
    async def test_fork_deleted_raises(self):
        repo = AsyncMock(spec=SkillRepositoryInterface)
        repo.find_by_id.return_value = _skill(user_id="2", status="deleted")
        uc = ForkSkillUseCase(repository=repo, dept_repo=_dept_repo(), logger=MagicMock())
        with pytest.raises(ValueError, match="삭제"):
            await uc.execute("skill-1", user_id="1", custom_name=None, request_id="req-1")

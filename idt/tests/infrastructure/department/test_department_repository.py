"""DepartmentRepository 단위 테스트 — AsyncMock 사용."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.department.entity import Department, UserDepartment
from src.infrastructure.department.department_repository import DepartmentRepository


def _make_dept(dept_id: str = "dept-1", name: str = "개발팀") -> Department:
    now = datetime.now(timezone.utc)
    return Department(
        id=dept_id, name=name, description="테스트 부서",
        created_at=now, updated_at=now,
    )


def _make_repo() -> tuple[DepartmentRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    logger = MagicMock()
    return DepartmentRepository(session=session, logger=logger), session


class TestDepartmentRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_model_and_flushes(self):
        repo, session = _make_repo()
        dept = _make_dept()
        result = await repo.save(dept, "req-1")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.id == dept.id

    @pytest.mark.asyncio
    async def test_save_propagates_exception(self):
        repo, session = _make_repo()
        session.flush = AsyncMock(side_effect=RuntimeError("DB error"))
        with pytest.raises(RuntimeError, match="DB error"):
            await repo.save(_make_dept(), "req-1")


class TestDepartmentRepositoryFindById:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_domain(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        mock_model = MagicMock()
        mock_model.id = "dept-1"
        mock_model.name = "개발팀"
        mock_model.description = "테스트"
        mock_model.created_at = now
        mock_model.updated_at = now
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        session.execute = AsyncMock(return_value=mock_result)

        dept = await repo.find_by_id("dept-1", "req-1")
        assert dept is not None
        assert dept.id == "dept-1"
        assert dept.name == "개발팀"

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_missing(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        assert await repo.find_by_id("not-exist", "req-1") is None


class TestDepartmentRepositoryAssignUser:
    @pytest.mark.asyncio
    async def test_assign_user_adds_and_flushes(self):
        repo, session = _make_repo()
        ud = UserDepartment(
            user_id=1, department_id="dept-1",
            is_primary=True, created_at=datetime.now(timezone.utc),
        )
        await repo.assign_user(ud, "req-1")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()


class TestDepartmentRepositoryCountPrimary:
    @pytest.mark.asyncio
    async def test_count_primary_returns_scalar(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.count_primary(1, "req-1")
        assert count == 1

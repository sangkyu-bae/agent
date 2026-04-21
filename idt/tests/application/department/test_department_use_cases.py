"""Department UseCases 단위 테스트 — Mock 의존성."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.department.create_department_use_case import CreateDepartmentUseCase
from src.application.department.list_departments_use_case import ListDepartmentsUseCase
from src.application.department.update_department_use_case import UpdateDepartmentUseCase
from src.application.department.delete_department_use_case import DeleteDepartmentUseCase
from src.application.department.assign_user_department_use_case import AssignUserDepartmentUseCase
from src.application.department.remove_user_department_use_case import RemoveUserDepartmentUseCase
from src.application.department.schemas import (
    AssignUserDepartmentRequest,
    CreateDepartmentRequest,
    UpdateDepartmentRequest,
)
from src.domain.department.entity import Department


NOW = datetime.now(timezone.utc)


def _make_dept(dept_id: str = "dept-1", name: str = "개발팀") -> Department:
    return Department(
        id=dept_id, name=name, description="테스트",
        created_at=NOW, updated_at=NOW,
    )


def _mock_repo():
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.find_by_id = AsyncMock()
    repo.find_by_name = AsyncMock()
    repo.list_all = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.assign_user = AsyncMock()
    repo.remove_user = AsyncMock()
    repo.count_primary = AsyncMock(return_value=0)
    repo.find_departments_by_user = AsyncMock(return_value=[])
    return repo


class TestCreateDepartmentUseCase:
    @pytest.mark.asyncio
    async def test_create_success(self):
        repo = _mock_repo()
        repo.find_by_name = AsyncMock(return_value=None)
        repo.save = AsyncMock(side_effect=lambda d, r: d)
        uc = CreateDepartmentUseCase(repository=repo, logger=MagicMock())
        req = CreateDepartmentRequest(name="개발팀", description="설명")
        result = await uc.execute(req, "req-1")
        assert result.name == "개발팀"
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_name_fails(self):
        repo = _mock_repo()
        repo.find_by_name = AsyncMock(return_value=_make_dept())
        uc = CreateDepartmentUseCase(repository=repo, logger=MagicMock())
        req = CreateDepartmentRequest(name="개발팀")
        with pytest.raises(ValueError, match="이미 존재"):
            await uc.execute(req, "req-1")


class TestListDepartmentsUseCase:
    @pytest.mark.asyncio
    async def test_list_returns_all(self):
        repo = _mock_repo()
        repo.list_all = AsyncMock(return_value=[_make_dept("d1", "A"), _make_dept("d2", "B")])
        uc = ListDepartmentsUseCase(repository=repo, logger=MagicMock())
        result = await uc.execute("req-1")
        assert len(result.departments) == 2


class TestUpdateDepartmentUseCase:
    @pytest.mark.asyncio
    async def test_update_success(self):
        repo = _mock_repo()
        dept = _make_dept()
        repo.find_by_id = AsyncMock(return_value=dept)
        repo.update = AsyncMock(side_effect=lambda d, r: d)
        uc = UpdateDepartmentUseCase(repository=repo, logger=MagicMock())
        req = UpdateDepartmentRequest(name="새이름")
        result = await uc.execute("dept-1", req, "req-1")
        assert result.name == "새이름"

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        repo = _mock_repo()
        repo.find_by_id = AsyncMock(return_value=None)
        uc = UpdateDepartmentUseCase(repository=repo, logger=MagicMock())
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("x", UpdateDepartmentRequest(name="a"), "req-1")


class TestDeleteDepartmentUseCase:
    @pytest.mark.asyncio
    async def test_delete_success(self):
        repo = _mock_repo()
        repo.find_by_id = AsyncMock(return_value=_make_dept())
        uc = DeleteDepartmentUseCase(repository=repo, logger=MagicMock())
        await uc.execute("dept-1", "req-1")
        repo.delete.assert_awaited_once_with("dept-1", "req-1")

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self):
        repo = _mock_repo()
        repo.find_by_id = AsyncMock(return_value=None)
        uc = DeleteDepartmentUseCase(repository=repo, logger=MagicMock())
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("x", "req-1")


class TestAssignUserDepartmentUseCase:
    @pytest.mark.asyncio
    async def test_assign_success(self):
        repo = _mock_repo()
        repo.find_by_id = AsyncMock(return_value=_make_dept())
        repo.count_primary = AsyncMock(return_value=0)
        uc = AssignUserDepartmentUseCase(repository=repo, logger=MagicMock())
        req = AssignUserDepartmentRequest(department_id="dept-1", is_primary=True)
        await uc.execute(1, req, "req-1")
        repo.assign_user.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assign_primary_limit(self):
        repo = _mock_repo()
        repo.find_by_id = AsyncMock(return_value=_make_dept())
        repo.count_primary = AsyncMock(return_value=1)
        uc = AssignUserDepartmentUseCase(repository=repo, logger=MagicMock())
        req = AssignUserDepartmentRequest(department_id="dept-1", is_primary=True)
        with pytest.raises(ValueError, match="primary"):
            await uc.execute(1, req, "req-1")


class TestRemoveUserDepartmentUseCase:
    @pytest.mark.asyncio
    async def test_remove_success(self):
        repo = _mock_repo()
        uc = RemoveUserDepartmentUseCase(repository=repo, logger=MagicMock())
        await uc.execute(1, "dept-1", "req-1")
        repo.remove_user.assert_awaited_once_with(1, "dept-1", "req-1")

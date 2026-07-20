"""GetUserDepartmentsUseCase 단위 테스트 (expose-user-department Design §3-1).

find_departments_by_user(링크) + list_all(부서명 해석)을 조합 → DepartmentBrief.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.application.department.get_user_departments_use_case import (
    GetUserDepartmentsUseCase,
)
from src.domain.department.entity import Department, UserDepartment


def _dept(dept_id: str, name: str) -> Department:
    return Department(
        id=dept_id, name=name, description=None,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _link(dept_id: str, is_primary: bool = False) -> UserDepartment:
    return UserDepartment(
        user_id=7, department_id=dept_id, is_primary=is_primary,
        created_at=datetime(2026, 1, 1),
    )


def _make(links, all_depts):
    repo = MagicMock()
    repo.find_departments_by_user = AsyncMock(return_value=links)
    repo.list_all = AsyncMock(return_value=all_depts)
    uc = GetUserDepartmentsUseCase(repository=repo, logger=MagicMock())
    return uc, repo


class TestExecute:
    async def test_소속_부서를_이름과_함께_반환(self):
        uc, _ = _make(
            [_link("d1", is_primary=True), _link("d2")],
            [_dept("d1", "여신심사팀"), _dept("d2", "여신기획팀")],
        )

        result = await uc.execute(7, "req-1")

        assert len(result) == 2
        assert result[0].id == "d1"
        assert result[0].name == "여신심사팀"
        assert result[0].is_primary is True
        assert result[1].name == "여신기획팀"

    async def test_미소속은_빈_리스트_부서조회_스킵(self):
        uc, repo = _make([], [_dept("d1", "여신심사팀")])

        result = await uc.execute(7, "req-1")

        assert result == []
        repo.list_all.assert_not_awaited()  # 링크 없으면 부서명 조회 불필요

    async def test_부서명_미존재시_id_폴백(self):
        uc, _ = _make([_link("d9")], [_dept("d1", "여신심사팀")])

        result = await uc.execute(7, "req-1")

        assert result[0].id == "d9"
        assert result[0].name == "d9"  # map에 없으면 id 폴백

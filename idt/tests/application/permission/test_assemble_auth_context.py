"""AssembleAuthContextUseCase 단위 테스트.

agent-user-context Design §4.2 + 테스트 전략 §10.1 검증:
- profile 없음 → email local-part fallback
- 부서 미배정 시 primary=None
- role + user 권한 합집합
- DB 미존재 user_id 등 에러 케이스
"""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.application.permission.assemble_auth_context import (
    AssembleAuthContextUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.department.entity import Department, UserDepartment
from src.domain.user_profile.entity import UserProfile


def _user(uid: int = 1, email: str = "hong@company.com", role: UserRole = UserRole.USER) -> User:
    return User(
        id=uid,
        email=email,
        password_hash="x",
        role=role,
        status=UserStatus.APPROVED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _logger():
    log = AsyncMock()
    log.info = lambda *a, **k: None
    log.warning = lambda *a, **k: None
    log.error = lambda *a, **k: None
    return log


def _make_uc(
    profile=None,
    user_departments=None,
    department_lookup=None,
    role_codes=None,
    user_codes=None,
) -> AssembleAuthContextUseCase:
    profile_repo = AsyncMock()
    profile_repo.find_by_user_id = AsyncMock(return_value=profile)

    department_repo = AsyncMock()
    department_repo.find_departments_by_user = AsyncMock(
        return_value=user_departments or []
    )

    async def _find_by_id(dept_id, _request_id):
        return (department_lookup or {}).get(dept_id)
    department_repo.find_by_id = _find_by_id

    permission_repo = AsyncMock()
    permission_repo.find_codes_for_role = AsyncMock(return_value=role_codes or [])
    permission_repo.find_codes_for_user = AsyncMock(return_value=user_codes or [])

    return AssembleAuthContextUseCase(
        profile_repo=profile_repo,
        department_repo=department_repo,
        permission_repo=permission_repo,
        logger=_logger(),
    )


class TestProfileFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_email_local_part(self):
        uc = _make_uc(profile=None)
        ctx = await uc.execute(_user(email="hong@company.com"), "req-1")
        assert ctx.display_name == "hong"

    @pytest.mark.asyncio
    async def test_uses_display_name_when_profile_exists(self):
        now = datetime.now(timezone.utc)
        profile = UserProfile(
            user_id=1, display_name="배상규",
            position="대리", employee_no="EMP-001",
            joined_at=date(2020, 1, 1),
            created_at=now, updated_at=now,
        )
        uc = _make_uc(profile=profile)
        ctx = await uc.execute(_user(), "req-1")
        assert ctx.display_name == "배상규"


class TestDepartmentAssembly:
    @pytest.mark.asyncio
    async def test_no_department_returns_none_primary(self):
        uc = _make_uc(user_departments=[])
        ctx = await uc.execute(_user(), "req-1")
        assert ctx.primary_department_id is None
        assert ctx.primary_department_name is None
        assert ctx.department_ids == ()
        assert ctx.department_names == ()

    @pytest.mark.asyncio
    async def test_multiple_departments_with_primary(self):
        now = datetime.now(timezone.utc)
        d1 = Department(id="d1", name="DX팀", description=None, created_at=now, updated_at=now)
        d2 = Department(id="d2", name="기획팀", description=None, created_at=now, updated_at=now)
        uc = _make_uc(
            user_departments=[
                UserDepartment(user_id=1, department_id="d1", is_primary=True,  created_at=now),
                UserDepartment(user_id=1, department_id="d2", is_primary=False, created_at=now),
            ],
            department_lookup={"d1": d1, "d2": d2},
        )
        ctx = await uc.execute(_user(), "req-1")
        assert ctx.primary_department_id == "d1"
        assert ctx.primary_department_name == "DX팀"
        assert set(ctx.department_ids) == {"d1", "d2"}
        assert set(ctx.department_names) == {"DX팀", "기획팀"}


class TestPermissionUnion:
    @pytest.mark.asyncio
    async def test_role_and_user_codes_unioned(self):
        uc = _make_uc(
            role_codes=["READ_PUBLIC_DOCS", "USE_RAG_SEARCH"],
            user_codes=["MANAGE_USERS"],
        )
        ctx = await uc.execute(_user(role=UserRole.ADMIN), "req-1")
        assert ctx.permissions == frozenset({
            "READ_PUBLIC_DOCS", "USE_RAG_SEARCH", "MANAGE_USERS",
        })

    @pytest.mark.asyncio
    async def test_user_id_none_raises(self):
        uc = _make_uc()
        user = User(
            id=None, email="a@a.com", password_hash="x",
            role=UserRole.USER, status=UserStatus.APPROVED,
        )
        with pytest.raises(ValueError):
            await uc.execute(user, "req-1")

    @pytest.mark.asyncio
    async def test_role_passed_to_permission_repo(self):
        uc = _make_uc(role_codes=[])
        await uc.execute(_user(role=UserRole.ADMIN), "req-1")
        uc._permission_repo.find_codes_for_role.assert_awaited_with("admin", "req-1")

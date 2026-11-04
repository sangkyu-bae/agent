"""ToolAccessResolver 테스트.

Design Ref: tool-access-control §0 F1 (auth_ctx 없는 경로는 user_id 로 조회), §3.5, §6.2
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_access.resolver import ToolAccessResolver
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.department.entity import UserDepartment
from src.domain.tool_access.value_objects import ToolAccessSet

A = "internal:excel_export"


def _ctx(role="user", user_id=12, depts=("d-loan",)) -> AuthContext:
    return AuthContext(
        user_id=user_id, display_name="u", role=role,
        primary_department_id=None, primary_department_name=None,
        department_ids=tuple(depts), department_names=(), permissions=frozenset(),
    )


def _user(role=UserRole.USER, status=UserStatus.APPROVED, uid=12) -> User:
    return User(email="u@x", password_hash="h", role=role, status=status, id=uid)


def _resolver(grants=frozenset({A}), user=None, depts=("d-loan",)):
    grant_repo = MagicMock()
    grant_repo.find_grants_for = AsyncMock(return_value=grants)
    user_repo = MagicMock()
    user_repo.find_by_id = AsyncMock(return_value=user)
    dept_repo = MagicMock()
    now = datetime.now(timezone.utc)
    dept_repo.find_departments_by_user = AsyncMock(
        return_value=[UserDepartment(12, d, i == 0, now) for i, d in enumerate(depts)]
    )
    r = ToolAccessResolver(
        grant_repo=grant_repo, user_repo=user_repo,
        department_repo=dept_repo, logger=MagicMock(),
    )
    return r, grant_repo, user_repo, dept_repo


class TestForAuthCtx:
    async def test_user_uses_ctx_departments_single_query(self):
        r, grant_repo, user_repo, dept_repo = _resolver()
        got = await r.for_auth_ctx(_ctx(depts=("d1", "d2")), "rid")
        assert got == ToolAccessSet(is_admin=False, allowed=frozenset({A}))
        grant_repo.find_grants_for.assert_awaited_once_with(12, ["d1", "d2"], "rid")
        user_repo.find_by_id.assert_not_awaited()
        dept_repo.find_departments_by_user.assert_not_awaited()

    async def test_admin_skips_query(self):
        r, grant_repo, *_ = _resolver()
        got = await r.for_auth_ctx(_ctx(role="admin"), "rid")
        assert got.is_admin
        grant_repo.find_grants_for.assert_not_awaited()

    @pytest.mark.parametrize("ctx", [None, AuthContext.public_anonymous()])
    async def test_missing_or_anonymous_is_deny_all(self, ctx):
        r, grant_repo, *_ = _resolver()
        assert await r.for_auth_ctx(ctx, "rid") == ToolAccessSet.deny_all()
        grant_repo.find_grants_for.assert_not_awaited()

    async def test_repo_error_propagates(self):
        # 실행 경로는 호출자가 deny_all 로 강등, 저장 경로는 실패시킨다 (§6.2)
        r, grant_repo, *_ = _resolver()
        grant_repo.find_grants_for.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            await r.for_auth_ctx(_ctx(), "rid")


class TestForUserId:
    async def test_looks_up_user_and_departments(self):
        r, grant_repo, user_repo, dept_repo = _resolver(user=_user(), depts=("d1", "d2"))
        got = await r.for_user_id("12", "rid")
        assert got.allowed == frozenset({A})
        user_repo.find_by_id.assert_awaited_once_with(12)
        dept_repo.find_departments_by_user.assert_awaited_once_with(12, "rid")
        grant_repo.find_grants_for.assert_awaited_once_with(12, ["d1", "d2"], "rid")

    async def test_accepts_int(self):
        r, *_ = _resolver(user=_user())
        assert (await r.for_user_id(12, "rid")).allowed == frozenset({A})

    async def test_admin_user(self):
        r, grant_repo, *_ = _resolver(user=_user(role=UserRole.ADMIN))
        assert (await r.for_user_id("12", "rid")).is_admin
        grant_repo.find_grants_for.assert_not_awaited()

    @pytest.mark.parametrize("raw", [None, "", "abc", "0", "-3", " "])
    async def test_invalid_id_is_deny_all(self, raw):
        r, _, user_repo, _ = _resolver(user=_user())
        assert await r.for_user_id(raw, "rid") == ToolAccessSet.deny_all()
        user_repo.find_by_id.assert_not_awaited()

    async def test_unknown_user_is_deny_all(self):
        r, grant_repo, *_ = _resolver(user=None)
        assert await r.for_user_id("12", "rid") == ToolAccessSet.deny_all()
        grant_repo.find_grants_for.assert_not_awaited()

    @pytest.mark.parametrize("status", [UserStatus.PENDING, UserStatus.REJECTED])
    async def test_not_approved_user_is_deny_all(self, status):
        r, grant_repo, *_ = _resolver(user=_user(status=status))
        assert await r.for_user_id("12", "rid") == ToolAccessSet.deny_all()
        grant_repo.find_grants_for.assert_not_awaited()

    async def test_not_approved_admin_is_deny_all(self):
        r, *_ = _resolver(user=_user(role=UserRole.ADMIN, status=UserStatus.PENDING))
        assert await r.for_user_id("12", "rid") == ToolAccessSet.deny_all()


class TestForUser:
    async def test_uses_given_user_without_lookup(self):
        r, _, user_repo, dept_repo = _resolver(depts=("d1",))
        got = await r.for_user(_user(), "rid")
        assert got.allowed == frozenset({A})
        user_repo.find_by_id.assert_not_awaited()
        dept_repo.find_departments_by_user.assert_awaited_once_with(12, "rid")

    async def test_user_without_id_is_deny_all(self):
        r, *_ = _resolver()
        assert await r.for_user(_user(uid=None), "rid") == ToolAccessSet.deny_all()

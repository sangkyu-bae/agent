"""관리자 도구 권한 UseCase 테스트.

Design Ref: tool-access-control §4.2 — 조회/전체 교체, 활성 카탈로그 기준 검증,
비활성 도구 규칙 보존(scope), 사용자 상속분(기본·부서) 출처.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_access.admin_use_cases import (
    DefaultToolAccessUseCase,
    DepartmentToolAccessUseCase,
    UserToolAccessUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.department.entity import Department, UserDepartment
from src.domain.tool_access.exceptions import UnknownToolIdsError
from src.domain.tool_access.interfaces import ToolAccessRepositoryInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry

A = "internal:excel_export"
B = "internal:python_code_executor"
C = "mcp:7f3c0000-0000-0000-0000-000000000001:search"
INACTIVE = "internal:document_generator"
NOW = datetime.now(timezone.utc)


class FakeGrantRepo(ToolAccessRepositoryInterface):
    def __init__(self) -> None:
        self.default: set[str] = set()
        self.dept: dict[str, set[str]] = {}
        self.user: dict[int, set[str]] = {}
        self.calls: list[tuple] = []

    async def find_grants_for(self, user_id, department_ids, request_id):
        out = set(self.default) | self.user.get(user_id, set())
        for d in department_ids:
            out |= self.dept.get(d, set())
        return frozenset(out)

    async def list_default(self, request_id):
        return sorted(self.default)

    async def list_for_department(self, department_id, request_id):
        return sorted(self.dept.get(department_id, set()))

    async def list_for_user(self, user_id, request_id):
        return sorted(self.user.get(user_id, set()))

    async def list_department_grants(self, department_ids, request_id):
        out: dict[str, list[str]] = {}
        for d in department_ids:
            for t in self.dept.get(d, set()):
                out.setdefault(t, []).append(d)
        return out

    @staticmethod
    def _apply(current: set[str], tool_ids, scope) -> set[str]:
        return {t for t in current if t not in scope} | {t for t in tool_ids if t in scope}

    async def replace_default(self, tool_ids, *, scope, granted_by, request_id):
        self.calls.append(("default", tuple(tool_ids), scope, granted_by))
        self.default = self._apply(self.default, tool_ids, scope)

    async def replace_for_department(self, department_id, tool_ids, *, scope, granted_by, request_id):
        self.calls.append(("dept", department_id, tuple(tool_ids), scope, granted_by))
        self.dept[department_id] = self._apply(self.dept.get(department_id, set()), tool_ids, scope)

    async def replace_for_user(self, user_id, tool_ids, *, scope, granted_by, request_id):
        self.calls.append(("user", user_id, tuple(tool_ids), scope, granted_by))
        self.user[user_id] = self._apply(self.user.get(user_id, set()), tool_ids, scope)


def _catalog(active=(A, B, C)):
    repo = MagicMock()
    repo.list_active = AsyncMock(return_value=[
        ToolCatalogEntry(id=t, tool_id=t, source="mcp" if t.startswith("mcp") else "internal",
                         name=t, description="")
        for t in active
    ])
    return repo


def _dept_repo(departments=None, memberships=None):
    departments = departments or {"d-loan": "여신부", "d-hr": "인사부"}
    repo = MagicMock()

    async def find_by_id(dept_id, request_id):
        name = departments.get(dept_id)
        return None if name is None else Department(dept_id, name, None, NOW, NOW)

    repo.find_by_id = AsyncMock(side_effect=find_by_id)
    repo.find_departments_by_user = AsyncMock(return_value=[
        UserDepartment(12, d, i == 0, NOW) for i, d in enumerate(memberships or [])
    ])
    return repo


def _user_repo(user):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=user)
    return repo


class TestDefault:
    async def test_replace_then_get(self):
        grants = FakeGrantRepo()
        uc = DefaultToolAccessUseCase(grants, _catalog(), MagicMock())
        got = await uc.replace([A, C], granted_by=1, request_id="r")
        assert got.tool_ids == [A, C]
        assert (await uc.get("r")).tool_ids == [A, C]

    async def test_storage_form_is_normalized(self):
        grants = FakeGrantRepo()
        uc = DefaultToolAccessUseCase(grants, _catalog(), MagicMock())
        got = await uc.replace(["excel_export"], granted_by=1, request_id="r")
        assert got.tool_ids == [A]

    async def test_unknown_or_inactive_ids_rejected(self):
        grants = FakeGrantRepo()
        uc = DefaultToolAccessUseCase(grants, _catalog(), MagicMock())
        with pytest.raises(UnknownToolIdsError) as ei:
            await uc.replace([A, INACTIVE, "mcp_legacy", "internal:nope"], granted_by=1, request_id="r")
        assert set(ei.value.tool_ids) == {INACTIVE, "mcp_legacy", "internal:nope"}
        assert grants.calls == []  # 하나라도 틀리면 아무것도 저장하지 않는다

    async def test_scope_is_active_catalog_and_granted_by_recorded(self):
        grants = FakeGrantRepo()
        uc = DefaultToolAccessUseCase(grants, _catalog(), MagicMock())
        await uc.replace([A], granted_by=7, request_id="r")
        _, _, scope, granted_by = grants.calls[0]
        assert scope == frozenset({A, B, C})
        assert granted_by == 7

    async def test_inactive_grant_preserved_but_hidden(self):
        grants = FakeGrantRepo()
        grants.default = {A, INACTIVE}
        uc = DefaultToolAccessUseCase(grants, _catalog(), MagicMock())
        assert (await uc.get("r")).tool_ids == [A]
        await uc.replace([B], granted_by=1, request_id="r")
        assert grants.default == {B, INACTIVE}


class TestDepartment:
    def _uc(self, grants):
        return DepartmentToolAccessUseCase(grants, _catalog(), _dept_repo(), MagicMock())

    async def test_get_includes_default_and_name(self):
        grants = FakeGrantRepo()
        grants.default = {A}
        grants.dept["d-loan"] = {B}
        got = await self._uc(grants).get("d-loan", "r")
        assert got.department_name == "여신부"
        assert got.tool_ids == [B]
        assert got.default_tool_ids == [A]

    async def test_unknown_department_raises_lookup(self):
        with pytest.raises(LookupError):
            await self._uc(FakeGrantRepo()).get("nope", "r")
        with pytest.raises(LookupError):
            await self._uc(FakeGrantRepo()).replace("nope", [A], granted_by=1, request_id="r")

    async def test_replace(self):
        grants = FakeGrantRepo()
        got = await self._uc(grants).replace("d-loan", [B, C], granted_by=1, request_id="r")
        assert got.tool_ids == [B, C]
        assert grants.dept["d-loan"] == {B, C}

    async def test_replace_rejects_unknown(self):
        grants = FakeGrantRepo()
        with pytest.raises(UnknownToolIdsError):
            await self._uc(grants).replace("d-loan", ["internal:nope"], granted_by=1, request_id="r")


class TestUser:
    def _uc(self, grants, user, memberships=("d-loan", "d-hr")):
        return UserToolAccessUseCase(
            grants, _catalog(), _user_repo(user), _dept_repo(memberships=list(memberships)), MagicMock(),
        )

    def _user(self, role=UserRole.USER):
        return User(email="u@x", password_hash="h", role=role, status=UserStatus.APPROVED, id=12)

    async def test_get_direct_and_inherited_sources(self):
        grants = FakeGrantRepo()
        grants.default = {A}
        grants.dept = {"d-loan": {A, B}, "d-hr": {B}}
        grants.user = {12: {C}}
        got = await self._uc(grants, self._user()).get(12, "r")
        assert got.is_admin is False
        assert got.tool_ids == [C]
        inherited = {i.tool_id: i for i in got.inherited}
        assert set(inherited) == {A, B}
        a_kinds = [(s.kind, s.department_id) for s in inherited[A].sources]
        assert a_kinds == [("default", None), ("department", "d-loan")]
        b_names = [s.department_name for s in inherited[B].sources]
        assert b_names == ["여신부", "인사부"]

    async def test_inherited_hides_inactive(self):
        grants = FakeGrantRepo()
        grants.default = {INACTIVE}
        got = await self._uc(grants, self._user()).get(12, "r")
        assert got.inherited == []

    async def test_admin_flag(self):
        got = await self._uc(FakeGrantRepo(), self._user(UserRole.ADMIN)).get(12, "r")
        assert got.is_admin is True

    async def test_unknown_user_raises_lookup(self):
        uc = self._uc(FakeGrantRepo(), None)
        with pytest.raises(LookupError):
            await uc.get(12, "r")
        with pytest.raises(LookupError):
            await uc.replace(12, [A], granted_by=1, request_id="r")

    async def test_replace(self):
        grants = FakeGrantRepo()
        got = await self._uc(grants, self._user()).replace(12, [B], granted_by=3, request_id="r")
        assert got.tool_ids == [B]
        assert grants.calls[0][0] == "user" and grants.calls[0][-1] == 3

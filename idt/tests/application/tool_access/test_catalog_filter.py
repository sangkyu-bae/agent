"""ListToolCatalogUseCase 권한 필터 테스트 (Plan FR-05, Design §8.2 L1-6~8)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.list_tool_catalog_use_case import ListToolCatalogUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.tool_access.value_objects import ToolAccessSet
from src.domain.tool_catalog.entity import ToolCatalogEntry

A = "internal:excel_export"
B = "internal:python_code_executor"
C = "mcp:7f3c0000-0000-0000-0000-000000000001:search"


def _repo():
    repo = MagicMock()
    repo.list_active = AsyncMock(return_value=[
        ToolCatalogEntry(id=t, tool_id=t, source="mcp" if t.startswith("mcp") else "internal",
                         name=t, description="")
        for t in (A, B, C)
    ])
    return repo


def _resolver(access: ToolAccessSet):
    r = MagicMock()
    r.for_user = AsyncMock(return_value=access)
    return r


VIEWER = User(email="u@x", password_hash="h", role=UserRole.USER, status=UserStatus.APPROVED, id=2)


async def test_without_resolver_returns_everything():
    uc = ListToolCatalogUseCase(repository=_repo(), logger=MagicMock())
    got = await uc.execute("r", viewer=VIEWER)
    assert [t.tool_id for t in got.tools] == [A, B, C]


async def test_filters_to_allowed_tools():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({A, C}))
    resolver = _resolver(access)
    uc = ListToolCatalogUseCase(repository=_repo(), logger=MagicMock(), access_resolver=resolver)
    got = await uc.execute("r", viewer=VIEWER)
    assert [t.tool_id for t in got.tools] == [A, C]
    resolver.for_user.assert_awaited_once_with(VIEWER, "r")


async def test_admin_gets_everything():
    uc = ListToolCatalogUseCase(
        repository=_repo(), logger=MagicMock(), access_resolver=_resolver(ToolAccessSet.admin())
    )
    got = await uc.execute("r", viewer=VIEWER)
    assert len(got.tools) == 3


async def test_resolver_without_viewer_is_fail_closed():
    uc = ListToolCatalogUseCase(
        repository=_repo(), logger=MagicMock(), access_resolver=_resolver(ToolAccessSet.admin())
    )
    got = await uc.execute("r")
    assert got.tools == []


async def test_resolver_error_propagates():
    resolver = MagicMock()
    resolver.for_user = AsyncMock(side_effect=RuntimeError("db"))
    uc = ListToolCatalogUseCase(repository=_repo(), logger=MagicMock(), access_resolver=resolver)
    with pytest.raises(RuntimeError):
        await uc.execute("r", viewer=VIEWER)

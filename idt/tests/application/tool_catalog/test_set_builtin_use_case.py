"""SetBuiltinToolUseCase 테스트 — builtin-tools D3."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.set_builtin_use_case import SetBuiltinToolUseCase
from src.domain.tool_catalog.entity import ToolCatalogEntry


def _entry(tool_id: str = "internal:wiki_read", **kw) -> ToolCatalogEntry:
    defaults = dict(
        id="tc-1", tool_id=tool_id, source="internal",
        name="위키 열람", description="d", is_active=True,
    )
    defaults.update(kw)
    return ToolCatalogEntry(**defaults)


def _use_case(found: ToolCatalogEntry | None):
    repo = MagicMock()
    repo.find_by_tool_id = AsyncMock(return_value=found)
    updated = None
    if found is not None:
        updated = _entry(found.tool_id, is_builtin=True)
    repo.set_builtin = AsyncMock(return_value=updated)
    return SetBuiltinToolUseCase(repository=repo, logger=MagicMock()), repo


class TestSetBuiltinToolUseCase:
    @pytest.mark.asyncio
    async def test_toggles_builtin_on(self):
        uc, repo = _use_case(found=_entry())
        result = await uc.execute("internal:wiki_read", True, "req")
        repo.set_builtin.assert_awaited_once_with("internal:wiki_read", True, "req")
        assert result.is_builtin is True

    @pytest.mark.asyncio
    async def test_unknown_tool_id_raises_value_error(self):
        uc, repo = _use_case(found=None)
        with pytest.raises(ValueError):
            await uc.execute("internal:nope", True, "req")
        repo.set_builtin.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inactive_tool_flag_allowed(self):
        """비활성 도구도 플래그 지정 허용 — 주입 시 active 필터가 방어(D5)."""
        uc, repo = _use_case(found=_entry(is_active=False))
        result = await uc.execute("internal:wiki_read", True, "req")
        assert result.is_builtin is True

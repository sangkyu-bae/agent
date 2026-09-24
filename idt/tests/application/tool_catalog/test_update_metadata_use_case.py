"""UpdateToolMetadataUseCase 단위 테스트.

Design Ref: mcp-tool-category-routing §4.2 (FR-02·FR-13) / §5 D-04

  관리자가 도구 분류·호출 상한을 지정하는 유스케이스. 검증은 도메인 정책
  (ToolCategoryPolicy)이 담당하고, 유스케이스는 '무엇을 갱신할지'만 정한다.

  부분 갱신: 인자를 생략하면 그 컬럼은 건드리지 않고, 명시적 None은
  '미분류로 되돌리기'다. 리포지토리의 UNSET 센티널이 둘을 가른다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.update_metadata_use_case import (
    UpdateToolMetadataUseCase,
)
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.interfaces import UNSET

MCP_TOOL_ID = "mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape"
LEGACY_TOOL_ID = "mcp_3f2a1b4c-0000-1111-2222-333344445555"


def _entry(tool_id=MCP_TOOL_ID, category=None, max_tool_calls=None):
    return ToolCatalogEntry(
        id="tc-1", tool_id=tool_id, source="mcp", name="scrape",
        description="d", category=category, max_tool_calls=max_tool_calls,
    )


def _make_uc(existing=None, updated=None):
    repo = MagicMock()
    repo.find_by_tool_id = AsyncMock(
        return_value=existing if existing is not None else _entry()
    )
    repo.update_metadata = AsyncMock(
        return_value=updated if updated is not None else _entry(category="collect")
    )
    return UpdateToolMetadataUseCase(repository=repo, logger=MagicMock()), repo


class TestUpdateToolMetadataSuccess:
    @pytest.mark.asyncio
    async def test_sets_category(self):
        uc, repo = _make_uc()

        result = await uc.execute(MCP_TOOL_ID, "req-1", category="collect")

        assert result.category == "collect"
        assert repo.update_metadata.await_args.kwargs["category"] == "collect"

    @pytest.mark.asyncio
    async def test_omitted_fields_are_not_updated(self):
        """부분 갱신: 넘기지 않은 인자는 UNSET으로 전달된다."""
        uc, repo = _make_uc()

        await uc.execute(MCP_TOOL_ID, "req-1", category="collect")

        assert repo.update_metadata.await_args.kwargs["max_tool_calls"] is UNSET

    @pytest.mark.asyncio
    async def test_explicit_none_clears_category(self):
        """명시적 None은 '미분류로 되돌리기' — UNSET과 구분된다."""
        uc, repo = _make_uc(updated=_entry(category=None))

        await uc.execute(MCP_TOOL_ID, "req-1", category=None)

        assert repo.update_metadata.await_args.kwargs["category"] is None

    @pytest.mark.asyncio
    async def test_sets_max_tool_calls_only(self):
        uc, repo = _make_uc(updated=_entry(max_tool_calls=5))

        result = await uc.execute(MCP_TOOL_ID, "req-1", max_tool_calls=5)

        assert result.max_tool_calls == 5
        assert repo.update_metadata.await_args.kwargs["category"] is UNSET

    @pytest.mark.asyncio
    async def test_sets_both_fields(self):
        uc, repo = _make_uc(updated=_entry(category="collect", max_tool_calls=3))

        await uc.execute(
            MCP_TOOL_ID, "req-1", category="collect", max_tool_calls=3,
        )

        kwargs = repo.update_metadata.await_args.kwargs
        assert kwargs["category"] == "collect"
        assert kwargs["max_tool_calls"] == 3


class TestUpdateToolMetadataValidation:
    @pytest.mark.asyncio
    async def test_rejects_unknown_category(self):
        uc, repo = _make_uc()

        with pytest.raises(ValueError):
            await uc.execute(MCP_TOOL_ID, "req-1", category="generate")

        repo.update_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_collect_on_server_level_tool(self):
        """D-04: 서버 단위 레거시 참조에는 collect를 지정할 수 없다."""
        uc, repo = _make_uc(existing=_entry(tool_id=LEGACY_TOOL_ID))

        with pytest.raises(ValueError) as exc:
            await uc.execute(LEGACY_TOOL_ID, "req-1", category="collect")

        assert "collect" in str(exc.value)
        repo.update_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allows_search_on_server_level_tool(self):
        uc, repo = _make_uc(
            existing=_entry(tool_id=LEGACY_TOOL_ID),
            updated=_entry(tool_id=LEGACY_TOOL_ID, category="search"),
        )

        await uc.execute(LEGACY_TOOL_ID, "req-1", category="search")

        repo.update_metadata.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejects_action_on_server_level_tool(self):
        """action-category-compose-node FR-03: action도 단일 도구 참조만 허용."""
        uc, repo = _make_uc(existing=_entry(tool_id=LEGACY_TOOL_ID))

        with pytest.raises(ValueError):
            await uc.execute(LEGACY_TOOL_ID, "req-1", category="action")

        repo.update_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_out_of_range_tool_calls(self):
        uc, repo = _make_uc()

        with pytest.raises(ValueError):
            await uc.execute(MCP_TOOL_ID, "req-1", max_tool_calls=0)

        repo.update_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_validation_runs_before_repository_read(self):
        """허용값 밖 카테고리는 존재 확인보다 먼저 거부한다(불필요한 조회 방지)."""
        uc, repo = _make_uc()

        with pytest.raises(ValueError):
            await uc.execute(MCP_TOOL_ID, "req-1", category="generate")

        repo.find_by_tool_id.assert_not_awaited()


class TestUpdateToolMetadataNotFound:
    """미존재는 LookupError로 구분한다 — 라우터가 404로, ValueError는 400으로
    번역할 수 있어야 한다 (§4.2 에러 표)."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_lookup_error(self):
        uc, repo = _make_uc(existing=None)
        repo.find_by_tool_id = AsyncMock(return_value=None)

        with pytest.raises(LookupError):
            await uc.execute("nope", "req-1", category="collect")

        repo.update_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_repository_returning_none_raises_lookup_error(self):
        """조회 직후 삭제된 경쟁 상황도 404로 수렴시킨다."""
        uc, repo = _make_uc()
        repo.update_metadata = AsyncMock(return_value=None)

        with pytest.raises(LookupError):
            await uc.execute(MCP_TOOL_ID, "req-1", category="collect")

    @pytest.mark.asyncio
    async def test_lookup_error_is_not_value_error(self):
        """두 예외가 겹치면 라우터가 400/404를 가릴 수 없다."""
        assert not issubclass(LookupError, ValueError)


class TestRequiresApprovalToggle:
    """approval-gate Check G2 — 관리자가 게이트를 켤 유일한 쓰기 경로.

    이 경로가 없으면 tool_catalog.requires_approval 을 DB 로 직접 UPDATE
    하지 않는 한 게이트가 발동할 방법이 없었다.
    """

    @pytest.mark.asyncio
    async def test_켜기가_리포지토리로_전달된다(self):
        uc, repo = _make_uc()
        await uc.execute(MCP_TOOL_ID, "req-1", requires_approval=True)
        assert repo.update_metadata.await_args.kwargs["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_끄기도_전달된다(self):
        uc, repo = _make_uc()
        await uc.execute(MCP_TOOL_ID, "req-1", requires_approval=False)
        assert repo.update_metadata.await_args.kwargs["requires_approval"] is False

    @pytest.mark.asyncio
    async def test_생략하면_UNSET으로_건드리지_않는다(self):
        """category 만 바꿀 때 승인 플래그가 딸려 바뀌면 안 된다."""
        uc, repo = _make_uc()
        await uc.execute(MCP_TOOL_ID, "req-1", category="collect")
        assert repo.update_metadata.await_args.kwargs["requires_approval"] is UNSET

    @pytest.mark.asyncio
    async def test_null은_거부한다(self):
        """NOT NULL 컬럼 — '되돌리기' 의미가 없다 (category 의 null 과 다름)."""
        uc, _ = _make_uc()
        with pytest.raises(ValueError):
            await uc.execute(MCP_TOOL_ID, "req-1", requires_approval=None)

    @pytest.mark.asyncio
    async def test_bool이_아니면_거부한다(self):
        uc, _ = _make_uc()
        with pytest.raises(ValueError):
            await uc.execute(MCP_TOOL_ID, "req-1", requires_approval="yes")

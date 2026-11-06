"""ToolFactory.create_all_async 의 서버 단위 허용 도구 필터 (tool-access-control FR-12, R9·R10)."""
import pytest

from tests.infrastructure.agent_builder.test_tool_factory import (
    TestToolFactoryCreateAllAsync as _Base,
    _SERVER_UUID,
)


class TestServerLevelAllowedNames:
    _tool = staticmethod(_Base._tool)
    _factory_with = _Base._factory_with

    def _three(self):
        return self._factory_with([self._tool("a"), self._tool("b"), self._tool("c")])

    @pytest.mark.asyncio
    async def test_binds_only_allowed_names(self):
        tools = await self._three().create_all_async(
            tool_id=f"mcp_{_SERVER_UUID}", request_id="r", allowed_tool_names=frozenset({"a", "c"}),
        )
        assert [t.mcp_tool_name for t in tools] == ["a", "c"]

    @pytest.mark.asyncio
    async def test_none_means_all(self):
        tools = await self._three().create_all_async(
            tool_id=f"mcp_{_SERVER_UUID}", request_id="r", allowed_tool_names=None,
        )
        assert len(tools) == 3

    @pytest.mark.asyncio
    async def test_no_overlap_raises_so_worker_is_isolated(self):
        # 컴파일러는 ValueError 를 워커 격리(failed_worker_ids)로 처리한다
        with pytest.raises(ValueError, match="permitted"):
            await self._three().create_all_async(
                tool_id=f"mcp_{_SERVER_UUID}", request_id="r", allowed_tool_names=frozenset({"zzz"}),
            )

    @pytest.mark.asyncio
    async def test_individual_reference_ignores_filter(self):
        tools = await self._three().create_all_async(
            tool_id=f"mcp:{_SERVER_UUID}:b", request_id="r", allowed_tool_names=frozenset({"a"}),
        )
        assert [t.mcp_tool_name for t in tools] == ["b"]

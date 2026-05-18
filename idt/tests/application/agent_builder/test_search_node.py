"""Search Node 단위 테스트 — LLM 없이 tool 직접 호출 검증 (TC-S01~S05)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _make_compiler() -> WorkflowCompiler:
    tool_factory = MagicMock(spec=ToolFactory)
    llm_factory = MagicMock()
    logger = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
    )


def _make_state(query: str = "AI 관련 뉴스", token_usage: int = 0) -> dict:
    msg = MagicMock()
    msg.content = query
    return {
        "messages": [msg],
        "token_usage": token_usage,
    }


class TestSearchNode:
    @pytest.mark.asyncio
    async def test_returns_result_with_worker_id_tag(self):
        """TC-S01: 검색 결과를 [worker_id 검색결과] 형식으로 반환."""
        compiler = _make_compiler()
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = "문서1: AI 기술 동향"

        node = compiler._create_search_node("doc_searcher", mock_tool)
        result = await node(_make_state())

        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert isinstance(msg, AIMessage)
        assert "[doc_searcher 검색결과]" in msg.content
        assert "문서1: AI 기술 동향" in msg.content

    @pytest.mark.asyncio
    async def test_sets_last_worker_id(self):
        """TC-S02: last_worker_id를 올바르게 설정."""
        compiler = _make_compiler()
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = "결과"

        node = compiler._create_search_node("my_worker", mock_tool)
        result = await node(_make_state())

        assert result["last_worker_id"] == "my_worker"

    @pytest.mark.asyncio
    async def test_increments_token_usage(self):
        """TC-S03: token_usage를 증가시킴."""
        compiler = _make_compiler()
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = "a" * 100

        node = compiler._create_search_node("w", mock_tool)
        result = await node(_make_state(token_usage=50))

        assert result["token_usage"] > 50

    @pytest.mark.asyncio
    async def test_tool_error_returns_error_message(self):
        """TC-S04: tool 예외 시 에러 메시지로 변환 (그래프 중단 없음)."""
        compiler = _make_compiler()
        mock_tool = AsyncMock()
        mock_tool.ainvoke.side_effect = RuntimeError("Connection timeout")

        node = compiler._create_search_node("w", mock_tool)
        result = await node(_make_state())

        msg = result["messages"][0]
        assert "검색 실패" in msg.content
        assert "Connection timeout" in msg.content

    @pytest.mark.asyncio
    async def test_does_not_call_llm(self):
        """TC-S05: Search Node가 LLM을 호출하지 않음."""
        compiler = _make_compiler()
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = "결과"

        node = compiler._create_search_node("w", mock_tool)
        await node(_make_state())

        compiler._llm_factory.create.assert_not_called()

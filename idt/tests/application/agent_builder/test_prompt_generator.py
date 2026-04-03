"""PromptGenerator 단위 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.prompt_generator import PromptGenerator
from src.domain.agent_builder.schemas import ToolMeta, WorkerDefinition, WorkflowSkeleton


def _make_skeleton() -> WorkflowSkeleton:
    return WorkflowSkeleton(
        workers=[
            WorkerDefinition(tool_id="tavily_search", worker_id="search_worker",
                             description="웹 검색", sort_order=0),
            WorkerDefinition(tool_id="excel_export", worker_id="export_worker",
                             description="엑셀 저장", sort_order=1),
        ],
        flow_hint="search 후 export",
    )


def _make_tool_metas() -> list[ToolMeta]:
    return [
        ToolMeta(tool_id="tavily_search", name="Tavily 웹 검색",
                 description="웹 검색 도구"),
        ToolMeta(tool_id="excel_export", name="Excel 파일 생성",
                 description="엑셀 저장 도구"),
    ]


def _make_generator() -> tuple[PromptGenerator, MagicMock]:
    mock_result = MagicMock()
    mock_result.content = "당신은 AI 뉴스 수집 에이전트입니다.\n\n[역할]\n- search_worker: 웹 검색"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_result)
    logger = MagicMock()
    return PromptGenerator(llm=mock_llm, logger=logger), mock_llm


class TestPromptGenerator:
    @pytest.mark.asyncio
    async def test_generate_returns_string(self):
        generator, _ = _make_generator()
        result = await generator.generate(
            "AI 뉴스 수집", _make_skeleton(), _make_tool_metas(), "req-1"
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_returns_llm_content(self):
        generator, _ = _make_generator()
        result = await generator.generate(
            "AI 뉴스 수집", _make_skeleton(), _make_tool_metas(), "req-1"
        )
        assert "에이전트" in result

    @pytest.mark.asyncio
    async def test_generate_calls_llm_with_user_request(self):
        generator, mock_llm = _make_generator()
        await generator.generate(
            "AI 뉴스 수집", _make_skeleton(), _make_tool_metas(), "req-1"
        )
        mock_llm.ainvoke.assert_called_once()
        messages = mock_llm.ainvoke.call_args[0][0]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "AI 뉴스 수집" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_generate_includes_worker_info_in_prompt(self):
        generator, mock_llm = _make_generator()
        await generator.generate(
            "AI 뉴스 수집", _make_skeleton(), _make_tool_metas(), "req-1"
        )
        messages = mock_llm.ainvoke.call_args[0][0]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "search_worker" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_generate_raises_on_llm_error(self):
        generator, mock_llm = _make_generator()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))
        with pytest.raises(RuntimeError, match="LLM error"):
            await generator.generate(
                "쿼리", _make_skeleton(), _make_tool_metas(), "req-1"
            )

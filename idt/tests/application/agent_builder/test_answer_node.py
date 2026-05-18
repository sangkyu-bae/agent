"""Answer Agent Node 단위 테스트 — 검색 결과 종합 답변 (TC-A01~A05)."""
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


def _make_state_with_search_results(
    user_query: str = "AI 기술 동향 알려줘",
    search_results: list[str] | None = None,
    token_usage: int = 0,
) -> dict:
    user_msg = {"role": "user", "content": user_query}

    messages: list = [user_msg]
    for sr in (search_results or []):
        msg = AIMessage(content=sr, name="search_worker")
        messages.append(msg)

    return {
        "messages": messages,
        "token_usage": token_usage,
    }


class TestAnswerNode:
    @pytest.mark.asyncio
    async def test_collects_search_results_by_tag(self):
        """TC-A01: 검색결과 태그가 있는 메시지만 수집."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="종합 답변입니다.")

        node = compiler._create_answer_node(mock_llm, "당신은 AI 에이전트입니다.")

        state = _make_state_with_search_results(
            search_results=[
                "[search_worker 검색결과]\n문서1: AI 기술",
                "[search_worker 검색결과]\n문서2: 최신 동향",
            ],
        )
        await node(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0]["content"]
        assert "문서1: AI 기술" in system_content
        assert "문서2: 최신 동향" in system_content

    @pytest.mark.asyncio
    async def test_includes_system_prompt_and_context(self):
        """TC-A02: system_prompt + 검색 결과 컨텍스트로 LLM 호출."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="답변")

        node = compiler._create_answer_node(mock_llm, "커스텀 프롬프트")

        state = _make_state_with_search_results(
            search_results=["[w 검색결과]\n데이터"],
        )
        await node(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0]["content"]
        assert "커스텀 프롬프트" in system_content

    @pytest.mark.asyncio
    async def test_extracts_user_query(self):
        """TC-A03: 원본 사용자 질문을 정확히 추출."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="답변")

        node = compiler._create_answer_node(mock_llm, "프롬프트")

        state = _make_state_with_search_results(
            user_query="금리 전망 알려줘",
            search_results=["[w 검색결과]\n데이터"],
        )
        await node(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        user_content = call_args[1]["content"]
        assert user_content == "금리 전망 알려줘"

    @pytest.mark.asyncio
    async def test_no_search_results_uses_fallback(self):
        """TC-A04: 검색 결과 없을 때 fallback 컨텍스트."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="답변")

        node = compiler._create_answer_node(mock_llm, "프롬프트")

        state = _make_state_with_search_results(search_results=[])
        await node(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0]["content"]
        assert "검색 결과 없음" in system_content

    @pytest.mark.asyncio
    async def test_last_worker_id_is_answer_agent(self):
        """TC-A05: last_worker_id == 'answer_agent'."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="답변")

        node = compiler._create_answer_node(mock_llm, "프롬프트")

        state = _make_state_with_search_results(
            search_results=["[w 검색결과]\n데이터"],
        )
        result = await node(state)

        assert result["last_worker_id"] == "answer_agent"

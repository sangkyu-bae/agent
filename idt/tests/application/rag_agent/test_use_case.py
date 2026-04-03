"""InternalDocumentSearchTool + RAGAgentUseCase 단위 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.hybrid_search.schemas import (
    HybridSearchResponse,
    HybridSearchResult,
)
from src.domain.rag_agent.schemas import RAGAgentRequest


# ──────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────

def _make_hybrid_result(
    content: str = "금융 정책 내용",
    source: str = "report.pdf",
    chunk_id: str = "c-1",
) -> HybridSearchResult:
    return HybridSearchResult(
        id=chunk_id,
        content=content,
        score=0.9,
        bm25_rank=1,
        bm25_score=10.0,
        vector_rank=1,
        vector_score=0.9,
        source="both",
        metadata={"source": source, "user_id": "u-1"},
    )


def _make_hybrid_response(results: list[HybridSearchResult]) -> HybridSearchResponse:
    return HybridSearchResponse(
        query="q",
        results=results,
        total_found=len(results),
        request_id="req-1",
    )


# ──────────────────────────────────────────────────────────
# InternalDocumentSearchTool
# ──────────────────────────────────────────────────────────

class TestInternalDocumentSearchTool:
    @pytest.mark.asyncio
    async def test_arun_returns_content_with_source(self):
        from src.application.rag_agent.tools import InternalDocumentSearchTool

        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_hybrid_response(
            [_make_hybrid_result(content="금융 정책 내용", source="report.pdf")]
        )

        tool = InternalDocumentSearchTool(
            hybrid_search_use_case=mock_uc, top_k=5, request_id="req-1"
        )
        output = await tool._arun("금융 정책")

        assert "금융 정책 내용" in output
        assert "report.pdf" in output

    @pytest.mark.asyncio
    async def test_arun_collects_sources(self):
        from src.application.rag_agent.tools import InternalDocumentSearchTool

        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_hybrid_response(
            [_make_hybrid_result(source="doc.pdf")]
        )

        tool = InternalDocumentSearchTool(
            hybrid_search_use_case=mock_uc, top_k=3, request_id="req-1"
        )
        await tool._arun("질문")

        assert len(tool.collected_sources) == 1
        assert tool.collected_sources[0].source == "doc.pdf"

    @pytest.mark.asyncio
    async def test_arun_equal_bm25_vector_top_k(self):
        """5:5 비율: bm25_top_k == vector_top_k."""
        from src.application.rag_agent.tools import InternalDocumentSearchTool
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_hybrid_response([])

        tool = InternalDocumentSearchTool(
            hybrid_search_use_case=mock_uc, top_k=5, request_id="req-1"
        )
        await tool._arun("질문")

        call_request: HybridSearchRequest = mock_uc.execute.call_args[0][0]
        assert call_request.bm25_top_k == call_request.vector_top_k

    @pytest.mark.asyncio
    async def test_arun_returns_no_result_message_when_empty(self):
        from src.application.rag_agent.tools import InternalDocumentSearchTool

        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_hybrid_response([])

        tool = InternalDocumentSearchTool(
            hybrid_search_use_case=mock_uc, top_k=5, request_id="req-1"
        )
        output = await tool._arun("찾을 수 없는 질문")
        assert "찾지 못" in output

    def test_run_raises_not_implemented(self):
        from src.application.rag_agent.tools import InternalDocumentSearchTool

        tool = InternalDocumentSearchTool(
            hybrid_search_use_case=MagicMock(), top_k=5, request_id="req-1"
        )
        with pytest.raises(NotImplementedError):
            tool._run("질문")


# ──────────────────────────────────────────────────────────
# RAGAgentUseCase
# ──────────────────────────────────────────────────────────

class TestRAGAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_answer(self):
        from src.application.rag_agent.use_case import RAGAgentUseCase
        from langchain_core.messages import AIMessage, HumanMessage

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                HumanMessage(content="질문"),
                AIMessage(content="내부 문서 기반 답변"),
            ]
        }

        with patch(
            "src.application.rag_agent.use_case.create_react_agent",
            return_value=mock_agent,
        ):
            uc = RAGAgentUseCase(
                hybrid_search_use_case=AsyncMock(),
                openai_api_key="test-key",
                model_name="gpt-4o-mini",
                logger=MagicMock(),
            )
            response = await uc.execute(
                RAGAgentRequest(query="질문", user_id="u-1"), "req-1"
            )

        assert response.answer == "내부 문서 기반 답변"
        assert response.request_id == "req-1"

    @pytest.mark.asyncio
    async def test_execute_detects_tool_use(self):
        from src.application.rag_agent.use_case import RAGAgentUseCase
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                HumanMessage(content="질문"),
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "internal_document_search",
                        "args": {"query": "질문"},
                        "id": "t-1",
                    }],
                ),
                ToolMessage(
                    content="결과",
                    tool_call_id="t-1",
                    name="internal_document_search",
                ),
                AIMessage(content="내부 문서 기반 답변"),
            ]
        }

        with patch(
            "src.application.rag_agent.use_case.create_react_agent",
            return_value=mock_agent,
        ):
            uc = RAGAgentUseCase(
                hybrid_search_use_case=AsyncMock(),
                openai_api_key="key",
                model_name="gpt-4o-mini",
                logger=MagicMock(),
            )
            response = await uc.execute(
                RAGAgentRequest(query="질문", user_id="u-1"), "req-1"
            )

        assert response.used_internal_docs is True

    @pytest.mark.asyncio
    async def test_execute_no_tool_use(self):
        from src.application.rag_agent.use_case import RAGAgentUseCase
        from langchain_core.messages import AIMessage, HumanMessage

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                HumanMessage(content="안녕"),
                AIMessage(content="안녕하세요!"),
            ]
        }

        with patch(
            "src.application.rag_agent.use_case.create_react_agent",
            return_value=mock_agent,
        ):
            uc = RAGAgentUseCase(
                hybrid_search_use_case=AsyncMock(),
                openai_api_key="key",
                model_name="gpt-4o-mini",
                logger=MagicMock(),
            )
            response = await uc.execute(
                RAGAgentRequest(query="안녕", user_id="u-1"), "req-2"
            )

        assert response.used_internal_docs is False
        assert response.answer == "안녕하세요!"

    @pytest.mark.asyncio
    async def test_execute_logs_start_and_complete(self):
        from src.application.rag_agent.use_case import RAGAgentUseCase
        from langchain_core.messages import AIMessage, HumanMessage

        mock_logger = MagicMock()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [HumanMessage(content="q"), AIMessage(content="a")]
        }

        with patch(
            "src.application.rag_agent.use_case.create_react_agent",
            return_value=mock_agent,
        ):
            uc = RAGAgentUseCase(
                hybrid_search_use_case=AsyncMock(),
                openai_api_key="key",
                model_name="gpt-4o-mini",
                logger=mock_logger,
            )
            await uc.execute(RAGAgentRequest(query="q", user_id="u-1"), "req-3")

        assert mock_logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_execute_logs_error_and_reraises(self):
        from src.application.rag_agent.use_case import RAGAgentUseCase

        mock_logger = MagicMock()
        mock_agent = AsyncMock()
        mock_agent.ainvoke.side_effect = RuntimeError("LLM 오류")

        with patch(
            "src.application.rag_agent.use_case.create_react_agent",
            return_value=mock_agent,
        ):
            uc = RAGAgentUseCase(
                hybrid_search_use_case=AsyncMock(),
                openai_api_key="key",
                model_name="gpt-4o-mini",
                logger=mock_logger,
            )
            with pytest.raises(RuntimeError):
                await uc.execute(RAGAgentRequest(query="q", user_id="u-1"), "req-4")

        mock_logger.error.assert_called_once()

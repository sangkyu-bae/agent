"""Tests for QueryGeneratorAdapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestQueryGeneratorAdapter:
    """LLM 기반 Multi-Query 생성 어댑터 테스트."""

    @pytest.fixture
    def mock_logger(self):
        logger = MagicMock()
        logger.info = MagicMock()
        logger.error = MagicMock()
        logger.warning = MagicMock()
        return logger

    @pytest.mark.asyncio
    async def test_generate_returns_list_of_strings(self, mock_logger) -> None:
        """생성 결과는 문자열 리스트."""
        from src.infrastructure.multi_query.query_generator_adapter import (
            QueryGeneratorAdapter,
        )
        from src.infrastructure.multi_query.schemas import MultiQueryGeneratorOutput

        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MultiQueryGeneratorOutput(
            queries=["저축은행 적금 이자율", "정기적금 금리 비교", "적금 우대 금리 조건"]
        )

        adapter = QueryGeneratorAdapter.__new__(QueryGeneratorAdapter)
        adapter._logger = mock_logger
        adapter._chain = mock_chain

        result = await adapter.generate(
            query="적금 금리", num_queries=3, request_id="req-001"
        )

        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(q, str) for q in result)

    @pytest.mark.asyncio
    async def test_generate_respects_num_queries(self, mock_logger) -> None:
        """num_queries에 맞는 개수를 반환."""
        from src.infrastructure.multi_query.query_generator_adapter import (
            QueryGeneratorAdapter,
        )
        from src.infrastructure.multi_query.schemas import MultiQueryGeneratorOutput

        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MultiQueryGeneratorOutput(
            queries=["q1", "q2", "q3", "q4", "q5"]
        )

        adapter = QueryGeneratorAdapter.__new__(QueryGeneratorAdapter)
        adapter._logger = mock_logger
        adapter._chain = mock_chain

        result = await adapter.generate(
            query="대출 한도", num_queries=5, request_id="req-002"
        )

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_generate_fallback_on_llm_error(self, mock_logger) -> None:
        """LLM 호출 실패 시 원본 쿼리를 담은 리스트 반환."""
        from src.infrastructure.multi_query.query_generator_adapter import (
            QueryGeneratorAdapter,
        )

        mock_chain = AsyncMock()
        mock_chain.ainvoke.side_effect = Exception("LLM API Error")

        adapter = QueryGeneratorAdapter.__new__(QueryGeneratorAdapter)
        adapter._logger = mock_logger
        adapter._chain = mock_chain

        result = await adapter.generate(
            query="적금 금리", num_queries=3, request_id="req-003"
        )

        assert result == ["적금 금리"]
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_filters_empty_queries(self, mock_logger) -> None:
        """빈 문자열 쿼리는 필터링."""
        from src.infrastructure.multi_query.query_generator_adapter import (
            QueryGeneratorAdapter,
        )
        from src.infrastructure.multi_query.schemas import MultiQueryGeneratorOutput

        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MultiQueryGeneratorOutput(
            queries=["valid query", "", "  ", "another valid"]
        )

        adapter = QueryGeneratorAdapter.__new__(QueryGeneratorAdapter)
        adapter._logger = mock_logger
        adapter._chain = mock_chain

        result = await adapter.generate(
            query="test", num_queries=4, request_id="req-004"
        )

        assert len(result) == 2
        assert "valid query" in result
        assert "another valid" in result

    @pytest.mark.asyncio
    async def test_generate_fallback_when_all_empty(self, mock_logger) -> None:
        """LLM이 빈 쿼리만 반환하면 원본 쿼리로 fallback."""
        from src.infrastructure.multi_query.query_generator_adapter import (
            QueryGeneratorAdapter,
        )
        from src.infrastructure.multi_query.schemas import MultiQueryGeneratorOutput

        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MultiQueryGeneratorOutput(
            queries=["", "  ", ""]
        )

        adapter = QueryGeneratorAdapter.__new__(QueryGeneratorAdapter)
        adapter._logger = mock_logger
        adapter._chain = mock_chain

        result = await adapter.generate(
            query="적금 금리", num_queries=3, request_id="req-005"
        )

        assert result == ["적금 금리"]

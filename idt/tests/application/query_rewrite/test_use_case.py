"""Tests for QueryRewriterUseCase."""

import pytest
from unittest.mock import AsyncMock

from src.application.query_rewrite.use_case import QueryRewriterUseCase
from src.domain.query_rewrite.value_objects import RewrittenQuery


class TestQueryRewriterUseCase:
    """Tests for QueryRewriterUseCase."""

    @pytest.fixture
    def mock_adapter(self) -> AsyncMock:
        """Create a mock adapter."""
        adapter = AsyncMock()
        adapter.rewrite = AsyncMock()
        return adapter

    @pytest.fixture
    def use_case(self, mock_adapter: AsyncMock) -> QueryRewriterUseCase:
        """Create use case with mocked adapter."""
        return QueryRewriterUseCase(rewriter_adapter=mock_adapter)

    async def test_rewrite_calls_adapter_with_stripped_query(
        self, use_case: QueryRewriterUseCase, mock_adapter: AsyncMock
    ) -> None:
        """Rewrite should call adapter with stripped query."""
        expected_result = RewrittenQuery(
            original_query="금리",
            rewritten_query="2024년 기준금리 정책"
        )
        mock_adapter.rewrite.return_value = expected_result

        result = await use_case.rewrite(
            query="  금리  ",
            request_id="test-123"
        )

        mock_adapter.rewrite.assert_called_once_with(
            query="금리",
            request_id="test-123"
        )
        assert result == expected_result

    async def test_rewrite_raises_value_error_with_empty_query(
        self, use_case: QueryRewriterUseCase
    ) -> None:
        """Rewrite with empty query should raise ValueError."""
        with pytest.raises(ValueError, match="Query is required"):
            await use_case.rewrite(
                query="",
                request_id="test-456"
            )

    async def test_rewrite_raises_value_error_with_too_short_query(
        self, use_case: QueryRewriterUseCase
    ) -> None:
        """Rewrite with too short query should raise ValueError."""
        with pytest.raises(ValueError, match="Query is too short"):
            await use_case.rewrite(
                query="a",
                request_id="test-789"
            )

    async def test_rewrite_raises_value_error_with_too_long_query(
        self, use_case: QueryRewriterUseCase
    ) -> None:
        """Rewrite with too long query should raise ValueError."""
        long_query = "a" * 1001
        with pytest.raises(ValueError, match="Query is too long"):
            await use_case.rewrite(
                query=long_query,
                request_id="test-long"
            )

    async def test_rewrite_raises_runtime_error_when_result_is_empty(
        self, use_case: QueryRewriterUseCase, mock_adapter: AsyncMock
    ) -> None:
        """Rewrite should raise RuntimeError when adapter returns empty result."""
        mock_adapter.rewrite.return_value = RewrittenQuery(
            original_query="테스트",
            rewritten_query=""
        )

        with pytest.raises(RuntimeError, match="Rewritten query is invalid"):
            await use_case.rewrite(
                query="테스트",
                request_id="test-empty-result"
            )

    async def test_rewrite_returns_adapter_result(
        self, use_case: QueryRewriterUseCase, mock_adapter: AsyncMock
    ) -> None:
        """Rewrite should return the result from adapter."""
        expected_result = RewrittenQuery(
            original_query="연금",
            rewritten_query="국민연금 수령 나이 정책"
        )
        mock_adapter.rewrite.return_value = expected_result

        result = await use_case.rewrite(
            query="연금",
            request_id="test-result"
        )

        assert result.original_query == "연금"
        assert result.rewritten_query == "국민연금 수령 나이 정책"

"""Tests for QueryRewriterAdapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.query_rewrite.adapter import QueryRewriterAdapter
from src.infrastructure.query_rewrite.schemas import QueryRewriteOutput
from src.domain.query_rewrite.value_objects import RewrittenQuery


class TestQueryRewriterAdapter:
    """Tests for QueryRewriterAdapter."""

    @pytest.fixture
    def mock_chain(self) -> MagicMock:
        """Create a mock chain."""
        return AsyncMock()

    @pytest.fixture
    def adapter_with_mock(self, mock_chain: MagicMock) -> QueryRewriterAdapter:
        """Create adapter with mocked chain."""
        with patch("src.infrastructure.query_rewrite.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            with patch.object(QueryRewriterAdapter, "_build_chain", return_value=mock_chain):
                adapter = QueryRewriterAdapter()
                adapter._chain = mock_chain
                return adapter

    async def test_rewrite_returns_rewritten_query(
        self, adapter_with_mock: QueryRewriterAdapter, mock_chain: MagicMock
    ) -> None:
        """Rewrite should return RewrittenQuery with original and rewritten query."""
        mock_chain.ainvoke.return_value = QueryRewriteOutput(
            rewritten_query="2024년 한국은행 기준금리 정책 변화"
        )

        result = await adapter_with_mock.rewrite(
            query="금리",
            request_id="test-request-123"
        )

        assert isinstance(result, RewrittenQuery)
        assert result.original_query == "금리"
        assert result.rewritten_query == "2024년 한국은행 기준금리 정책 변화"

    async def test_rewrite_passes_query_to_chain(
        self, adapter_with_mock: QueryRewriterAdapter, mock_chain: MagicMock
    ) -> None:
        """Rewrite should pass query to chain in correct format."""
        mock_chain.ainvoke.return_value = QueryRewriteOutput(
            rewritten_query="국민연금 수령 나이 변경 정책"
        )

        await adapter_with_mock.rewrite(
            query="연금 나이",
            request_id="test-request-456"
        )

        mock_chain.ainvoke.assert_called_once()
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "query" in call_args
        assert call_args["query"] == "연금 나이"

    async def test_rewrite_raises_exception_on_llm_error(
        self, adapter_with_mock: QueryRewriterAdapter, mock_chain: MagicMock
    ) -> None:
        """Rewrite should propagate exceptions from LLM."""
        mock_chain.ainvoke.side_effect = Exception("LLM API error")

        with pytest.raises(Exception, match="LLM API error"):
            await adapter_with_mock.rewrite(
                query="테스트 쿼리",
                request_id="test-request-error"
            )


class TestQueryRewriterAdapterInit:
    """Tests for QueryRewriterAdapter initialization."""

    def test_default_model_name(self) -> None:
        """Adapter should use gpt-4o-mini as default model."""
        with patch("src.infrastructure.query_rewrite.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = QueryRewriterAdapter()
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_default_temperature(self) -> None:
        """Adapter should use temperature=0.0 as default."""
        with patch("src.infrastructure.query_rewrite.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = QueryRewriterAdapter()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.0

    def test_custom_model_name(self) -> None:
        """Adapter should accept custom model name."""
        with patch("src.infrastructure.query_rewrite.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = QueryRewriterAdapter(model_name="gpt-4o")
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"

    def test_custom_temperature(self) -> None:
        """Adapter should accept custom temperature."""
        with patch("src.infrastructure.query_rewrite.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = QueryRewriterAdapter(temperature=0.5)
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.5

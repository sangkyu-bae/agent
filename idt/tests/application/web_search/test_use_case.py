"""Tests for WebSearchUseCase."""

from unittest.mock import MagicMock, patch

import pytest

from src.application.web_search.use_case import WebSearchUseCase
from src.domain.web_search.policy import WebSearchPolicy
from src.domain.web_search.value_objects import SearchResult, SearchResultItem


class TestWebSearchUseCase:
    """Tests for WebSearchUseCase."""

    class TestSearch:
        """Tests for search method."""

        @pytest.fixture
        def mock_tool(self) -> MagicMock:
            """Create a mock TavilySearchTool."""
            tool = MagicMock()
            tool.search.return_value = '{"title": "Test"}'
            return tool

        @pytest.fixture
        def use_case(self, mock_tool: MagicMock) -> WebSearchUseCase:
            """Create a use case with mock tool."""
            return WebSearchUseCase(search_tool=mock_tool)

        def test_search_calls_tool_with_stripped_query(
            self, use_case: WebSearchUseCase, mock_tool: MagicMock
        ) -> None:
            """search should strip whitespace from query before calling tool."""
            use_case.search("  test query  ", request_id="test-123")

            mock_tool.search.assert_called_once()
            call_kwargs = mock_tool.search.call_args[1]
            assert call_kwargs["query"] == "test query"

        def test_search_raises_value_error_with_short_query(
            self, use_case: WebSearchUseCase
        ) -> None:
            """search should raise ValueError for query shorter than minimum."""
            with pytest.raises(ValueError, match="Query is too short"):
                use_case.search("abc", request_id="test-123")

        def test_search_raises_value_error_with_empty_query(
            self, use_case: WebSearchUseCase
        ) -> None:
            """search should raise ValueError for empty query."""
            with pytest.raises(ValueError, match="Query is too short"):
                use_case.search("", request_id="test-123")

        def test_search_raises_value_error_with_whitespace_only_query(
            self, use_case: WebSearchUseCase
        ) -> None:
            """search should raise ValueError for whitespace-only query."""
            with pytest.raises(ValueError, match="Query is too short"):
                use_case.search("   ", request_id="test-123")

        def test_search_passes_max_results_to_tool(
            self, use_case: WebSearchUseCase, mock_tool: MagicMock
        ) -> None:
            """search should pass max_results parameter to tool."""
            use_case.search("test query", request_id="test-123", max_results=5)

            call_kwargs = mock_tool.search.call_args[1]
            assert call_kwargs["max_results"] == 5

        def test_search_passes_all_parameters_to_tool(
            self, use_case: WebSearchUseCase, mock_tool: MagicMock
        ) -> None:
            """search should pass all parameters to tool."""
            use_case.search(
                "test query",
                request_id="test-123",
                max_results=5,
                search_depth="advanced",
                topic="news",
                include_raw_content=True,
                days=7,
                format_output=True,
            )

            call_kwargs = mock_tool.search.call_args[1]
            assert call_kwargs["query"] == "test query"
            assert call_kwargs["request_id"] == "test-123"
            assert call_kwargs["max_results"] == 5
            assert call_kwargs["search_depth"] == "advanced"
            assert call_kwargs["topic"] == "news"
            assert call_kwargs["include_raw_content"] is True
            assert call_kwargs["days"] == 7
            assert call_kwargs["format_output"] is True

    class TestGetContext:
        """Tests for get_context method."""

        @pytest.fixture
        def mock_tool(self) -> MagicMock:
            """Create a mock TavilySearchTool."""
            tool = MagicMock()
            tool.get_search_context.return_value = "Context string"
            return tool

        @pytest.fixture
        def use_case(self, mock_tool: MagicMock) -> WebSearchUseCase:
            """Create a use case with mock tool."""
            return WebSearchUseCase(search_tool=mock_tool)

        def test_get_context_returns_json_string(
            self, use_case: WebSearchUseCase, mock_tool: MagicMock
        ) -> None:
            """get_context should return string context."""
            result = use_case.get_context("test query", request_id="test-123")

            assert isinstance(result, str)
            assert "Context string" in result

        def test_get_context_raises_value_error_with_invalid_query(
            self, use_case: WebSearchUseCase
        ) -> None:
            """get_context should raise ValueError for invalid query."""
            with pytest.raises(ValueError, match="Query is too short"):
                use_case.get_context("abc", request_id="test-123")

        def test_get_context_passes_parameters_to_tool(
            self, use_case: WebSearchUseCase, mock_tool: MagicMock
        ) -> None:
            """get_context should pass all parameters to tool."""
            use_case.get_context(
                "test query",
                request_id="test-123",
                max_results=5,
                max_tokens=2000,
            )

            call_kwargs = mock_tool.get_search_context.call_args[1]
            assert call_kwargs["query"] == "test query"
            assert call_kwargs["request_id"] == "test-123"
            assert call_kwargs["max_results"] == 5
            assert call_kwargs["max_tokens"] == 2000

    class TestSearchAsValueObject:
        """Tests for search_as_value_object method."""

        @pytest.fixture
        def mock_tool(self) -> MagicMock:
            """Create a mock TavilySearchTool."""
            tool = MagicMock()
            tool.search_as_value_object.return_value = SearchResult(
                query="test query",
                items=[
                    SearchResultItem(
                        title="Test",
                        url="https://example.com",
                        content="Content",
                        score=0.95,
                    )
                ],
            )
            return tool

        @pytest.fixture
        def use_case(self, mock_tool: MagicMock) -> WebSearchUseCase:
            """Create a use case with mock tool."""
            return WebSearchUseCase(search_tool=mock_tool)

        def test_search_as_value_object_returns_search_result(
            self, use_case: WebSearchUseCase
        ) -> None:
            """search_as_value_object should return SearchResult."""
            result = use_case.search_as_value_object(
                "test query", request_id="test-123"
            )

            assert isinstance(result, SearchResult)
            assert result.query == "test query"

        def test_search_as_value_object_raises_value_error_with_invalid_query(
            self, use_case: WebSearchUseCase
        ) -> None:
            """search_as_value_object should raise ValueError for invalid query."""
            with pytest.raises(ValueError, match="Query is too short"):
                use_case.search_as_value_object("abc", request_id="test-123")

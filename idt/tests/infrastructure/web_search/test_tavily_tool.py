"""Tests for TavilySearchTool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.web_search.policy import WebSearchPolicy
from src.domain.web_search.value_objects import SearchResult
from src.infrastructure.web_search.tavily_tool import TavilySearchTool


class TestTavilySearchToolInit:
    """Tests for TavilySearchTool initialization."""

    def test_init_raises_error_without_api_key(self) -> None:
        """Initialization should raise error when no API key provided."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="TAVILY_API_KEY"):
                TavilySearchTool()

    def test_init_uses_env_var_when_api_key_not_provided(self) -> None:
        """Initialization should use environment variable for API key."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool()
            assert tool._api_key == "test-api-key"

    def test_init_uses_provided_api_key_over_env_var(self) -> None:
        """Initialization should prefer provided API key over env var."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "env-api-key"}):
            tool = TavilySearchTool(api_key="provided-api-key")
            assert tool._api_key == "provided-api-key"

    def test_init_validates_max_results_with_policy(self) -> None:
        """Initialization should validate max_results using policy."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool(max_results=20)
            assert tool._max_results == WebSearchPolicy.MAX_RESULTS_LIMIT

    def test_init_sets_default_max_results(self) -> None:
        """Initialization should set default max_results from policy."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool()
            assert tool._max_results == WebSearchPolicy.DEFAULT_MAX_RESULTS


class TestTavilySearchToolSearch:
    """Tests for TavilySearchTool.search method."""

    @pytest.fixture
    def mock_tavily_client(self) -> MagicMock:
        """Create a mock Tavily client."""
        client = MagicMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "Test content",
                    "score": 0.95,
                    "raw_content": None,
                }
            ]
        }
        return client

    @pytest.fixture
    def tool_with_mock(self, mock_tavily_client: MagicMock) -> TavilySearchTool:
        """Create a tool with mocked Tavily client."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool()
            tool._client = mock_tavily_client
            return tool

    def test_search_returns_results(self, tool_with_mock: TavilySearchTool) -> None:
        """search method should return string results."""
        result = tool_with_mock.search("test query", request_id="test-123")

        assert isinstance(result, str)
        assert "Test Result" in result

    def test_search_with_format_output_returns_xml(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """search method with format_output should return XML."""
        result = tool_with_mock.search(
            "test query", request_id="test-123", format_output=True
        )

        assert "<search_results>" in result
        assert "<title>Test Result</title>" in result

    def test_search_logs_warning_for_days_with_general_topic(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """search should log warning when days is used with general topic."""
        with patch(
            "src.infrastructure.web_search.tavily_tool.get_logger"
        ) as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            tool_with_mock.search(
                "test query", request_id="test-123", topic="general", days=7
            )

            mock_logger.warning.assert_called()

    def test_search_logs_start_and_completion(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """search should log start and completion INFO messages."""
        with patch(
            "src.infrastructure.web_search.tavily_tool.get_logger"
        ) as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            tool_with_mock.search("test query", request_id="test-123")

            assert mock_logger.info.call_count >= 2

    def test_search_logs_error_on_exception(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """search should log error when exception occurs."""
        tool_with_mock._client.search.side_effect = Exception("API Error")

        with patch(
            "src.infrastructure.web_search.tavily_tool.get_logger"
        ) as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            with pytest.raises(Exception):
                tool_with_mock.search("test query", request_id="test-123")

            mock_logger.error.assert_called()


class TestTavilySearchToolSearchAsValueObject:
    """Tests for TavilySearchTool.search_as_value_object method."""

    @pytest.fixture
    def mock_tavily_client(self) -> MagicMock:
        """Create a mock Tavily client."""
        client = MagicMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "Test content",
                    "score": 0.95,
                    "raw_content": "Full content",
                }
            ]
        }
        return client

    @pytest.fixture
    def tool_with_mock(self, mock_tavily_client: MagicMock) -> TavilySearchTool:
        """Create a tool with mocked Tavily client."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool()
            tool._client = mock_tavily_client
            return tool

    def test_search_as_value_object_returns_search_result(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """search_as_value_object should return SearchResult."""
        result = tool_with_mock.search_as_value_object(
            "test query", request_id="test-123"
        )

        assert isinstance(result, SearchResult)
        assert result.query == "test query"
        assert result.result_count == 1
        assert result.items[0].title == "Test Result"


class TestTavilySearchToolGetSearchContext:
    """Tests for TavilySearchTool.get_search_context method."""

    @pytest.fixture
    def mock_tavily_client(self) -> MagicMock:
        """Create a mock Tavily client."""
        client = MagicMock()
        client.get_search_context.return_value = "Context string from Tavily"
        return client

    @pytest.fixture
    def tool_with_mock(self, mock_tavily_client: MagicMock) -> TavilySearchTool:
        """Create a tool with mocked Tavily client."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool()
            tool._client = mock_tavily_client
            return tool

    def test_get_search_context_returns_json_string(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """get_search_context should return string context."""
        result = tool_with_mock.get_search_context(
            "test query", request_id="test-123"
        )

        assert isinstance(result, str)
        assert "Context string from Tavily" in result

    def test_get_search_context_with_max_tokens(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """get_search_context should pass max_tokens to client."""
        tool_with_mock.get_search_context(
            "test query", request_id="test-123", max_tokens=1000
        )

        tool_with_mock._client.get_search_context.assert_called_once()
        call_kwargs = tool_with_mock._client.get_search_context.call_args[1]
        assert call_kwargs["max_tokens"] == 1000


class TestTavilySearchToolRun:
    """Tests for TavilySearchTool._run method (LangChain integration)."""

    @pytest.fixture
    def mock_tavily_client(self) -> MagicMock:
        """Create a mock Tavily client."""
        client = MagicMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "Test content",
                    "score": 0.95,
                    "raw_content": None,
                }
            ]
        }
        return client

    @pytest.fixture
    def tool_with_mock(self, mock_tavily_client: MagicMock) -> TavilySearchTool:
        """Create a tool with mocked Tavily client."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool()
            tool._client = mock_tavily_client
            return tool

    def test_run_calls_search_with_parameters(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """_run should call search with provided parameters."""
        result = tool_with_mock._run(
            query="test query",
            search_depth="basic",
            topic="general",
            max_results=5,
            include_raw_content=False,
        )

        assert isinstance(result, str)
        tool_with_mock._client.search.assert_called_once()


class TestTavilySearchToolAsyncRun:
    """Tests for TavilySearchTool._arun method (async LangChain integration)."""

    @pytest.fixture
    def mock_tavily_client(self) -> MagicMock:
        """Create a mock Tavily client."""
        client = MagicMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "Test content",
                    "score": 0.95,
                    "raw_content": None,
                }
            ]
        }
        return client

    @pytest.fixture
    def tool_with_mock(self, mock_tavily_client: MagicMock) -> TavilySearchTool:
        """Create a tool with mocked Tavily client."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-api-key"}):
            tool = TavilySearchTool()
            tool._client = mock_tavily_client
            return tool

    @pytest.mark.asyncio
    async def test_arun_calls_search(
        self, tool_with_mock: TavilySearchTool
    ) -> None:
        """_arun should call search method."""
        result = await tool_with_mock._arun(
            query="test query",
            search_depth="basic",
            topic="general",
            max_results=5,
            include_raw_content=False,
        )

        assert isinstance(result, str)

"""Web search use case."""

from typing import Literal

from src.domain.web_search.policy import WebSearchPolicy
from src.domain.web_search.value_objects import SearchResult
from src.infrastructure.logging import get_logger
from src.infrastructure.web_search.tavily_tool import TavilySearchTool


class WebSearchUseCase:
    """Use case for web search operations.

    Orchestrates web search functionality with validation and logging.
    """

    def __init__(self, search_tool: TavilySearchTool) -> None:
        """Initialize WebSearchUseCase.

        Args:
            search_tool: The search tool to use for web searches.
        """
        self._search_tool = search_tool
        self._logger = get_logger(__name__)

    def search(
        self,
        query: str,
        request_id: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: Literal["general", "news"] = "general",
        max_results: int | None = None,
        include_raw_content: bool = False,
        days: int | None = None,
        format_output: bool = False,
    ) -> str:
        """Execute a web search.

        Args:
            query: Search query.
            request_id: Request ID for logging.
            search_depth: Search depth level.
            topic: Topic type for search.
            max_results: Maximum number of results.
            include_raw_content: Whether to include raw content.
            days: Number of days to search back (news topic only).
            format_output: Whether to format output as XML.

        Returns:
            Search results as string.

        Raises:
            ValueError: If query is invalid.
        """
        stripped_query = query.strip() if query else ""

        if not WebSearchPolicy.validate_query(stripped_query):
            self._logger.warning(
                "Invalid search query",
                request_id=request_id,
                query_length=len(stripped_query),
            )
            raise ValueError(
                f"Query is too short. Minimum length is "
                f"{WebSearchPolicy.MIN_QUERY_LENGTH} characters."
            )

        self._logger.info(
            "Web search use case started",
            request_id=request_id,
            query=stripped_query[:100],
        )

        result = self._search_tool.search(
            query=stripped_query,
            request_id=request_id,
            search_depth=search_depth,
            topic=topic,
            max_results=max_results,
            include_raw_content=include_raw_content,
            days=days,
            format_output=format_output,
        )

        self._logger.info(
            "Web search use case completed",
            request_id=request_id,
        )

        return result

    def search_as_value_object(
        self,
        query: str,
        request_id: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: Literal["general", "news"] = "general",
        max_results: int | None = None,
        include_raw_content: bool = False,
        days: int | None = None,
    ) -> SearchResult:
        """Execute a web search and return as value object.

        Args:
            query: Search query.
            request_id: Request ID for logging.
            search_depth: Search depth level.
            topic: Topic type for search.
            max_results: Maximum number of results.
            include_raw_content: Whether to include raw content.
            days: Number of days to search back (news topic only).

        Returns:
            SearchResult value object.

        Raises:
            ValueError: If query is invalid.
        """
        stripped_query = query.strip() if query else ""

        if not WebSearchPolicy.validate_query(stripped_query):
            raise ValueError(
                f"Query is too short. Minimum length is "
                f"{WebSearchPolicy.MIN_QUERY_LENGTH} characters."
            )

        return self._search_tool.search_as_value_object(
            query=stripped_query,
            request_id=request_id,
            search_depth=search_depth,
            topic=topic,
            max_results=max_results,
            include_raw_content=include_raw_content,
            days=days,
        )

    def get_context(
        self,
        query: str,
        request_id: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: Literal["general", "news"] = "general",
        max_results: int | None = None,
        max_tokens: int = 4000,
        days: int | None = None,
    ) -> str:
        """Get search context for LLM consumption.

        Args:
            query: Search query.
            request_id: Request ID for logging.
            search_depth: Search depth level.
            topic: Topic type for search.
            max_results: Maximum number of results.
            max_tokens: Maximum tokens in context.
            days: Number of days to search back (news topic only).

        Returns:
            Context string for LLM.

        Raises:
            ValueError: If query is invalid.
        """
        stripped_query = query.strip() if query else ""

        if not WebSearchPolicy.validate_query(stripped_query):
            raise ValueError(
                f"Query is too short. Minimum length is "
                f"{WebSearchPolicy.MIN_QUERY_LENGTH} characters."
            )

        return self._search_tool.get_search_context(
            query=stripped_query,
            request_id=request_id,
            search_depth=search_depth,
            topic=topic,
            max_results=max_results,
            max_tokens=max_tokens,
            days=days,
        )

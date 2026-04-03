"""Tavily web search tool implementation."""

import json
import os
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import Field
from tavily import TavilyClient

from src.domain.web_search.policy import WebSearchPolicy
from src.domain.web_search.value_objects import SearchResult, SearchResultItem
from src.infrastructure.logging import get_logger
from src.infrastructure.web_search.formatter import format_search_result_to_xml
from src.infrastructure.web_search.schemas import TavilySearchInput


class TavilySearchTool(BaseTool):
    """LangChain-compatible Tavily web search tool.

    Provides web search capabilities using the Tavily API.
    """

    name: str = "tavily_search"
    description: str = (
        "Search the web for current information. "
        "Use this when you need up-to-date information from the internet."
    )
    args_schema: type = TavilySearchInput

    _api_key: str
    _client: TavilyClient
    _max_results: int

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize TavilySearchTool.

        Args:
            api_key: Tavily API key. Falls back to TAVILY_API_KEY env var.
            max_results: Default maximum number of results.
            **kwargs: Additional arguments passed to BaseTool.

        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        super().__init__(**kwargs)

        resolved_api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "TAVILY_API_KEY must be provided or set in environment variables"
            )

        self._api_key = resolved_api_key
        self._client = TavilyClient(api_key=resolved_api_key)
        self._max_results = WebSearchPolicy.validate_max_results(max_results)

    def _run(
        self,
        query: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: Literal["general", "news"] = "general",
        max_results: int | None = None,
        include_raw_content: bool = False,
        days: int | None = None,
    ) -> str:
        """Execute the tool (LangChain interface).

        Args:
            query: Search query.
            search_depth: Search depth level.
            topic: Topic type for search.
            max_results: Maximum number of results.
            include_raw_content: Whether to include raw content.
            days: Number of days to search back (news topic only).

        Returns:
            Formatted search results string.
        """
        return self.search(
            query=query,
            request_id="langchain-run",
            search_depth=search_depth,
            topic=topic,
            max_results=max_results,
            include_raw_content=include_raw_content,
            days=days,
            format_output=True,
        )

    async def _arun(
        self,
        query: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: Literal["general", "news"] = "general",
        max_results: int | None = None,
        include_raw_content: bool = False,
        days: int | None = None,
    ) -> str:
        """Execute the tool asynchronously (LangChain interface).

        Args:
            query: Search query.
            search_depth: Search depth level.
            topic: Topic type for search.
            max_results: Maximum number of results.
            include_raw_content: Whether to include raw content.
            days: Number of days to search back (news topic only).

        Returns:
            Formatted search results string.
        """
        return self._run(
            query=query,
            search_depth=search_depth,
            topic=topic,
            max_results=max_results,
            include_raw_content=include_raw_content,
            days=days,
        )

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
        """Perform a web search.

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
            Search results as string (JSON or XML based on format_output).

        Raises:
            Exception: If search fails.
        """
        logger = get_logger(__name__)

        truncated_query = query[:100] + "..." if len(query) > 100 else query
        logger.info(
            "Web search started",
            request_id=request_id,
            query=truncated_query,
            topic=topic,
            search_depth=search_depth,
        )

        if days is not None and topic == "general":
            logger.warning(
                "days parameter is only effective with 'news' topic",
                request_id=request_id,
                days=days,
                topic=topic,
            )

        validated_max_results = WebSearchPolicy.validate_max_results(
            max_results or self._max_results
        )

        try:
            search_kwargs: dict[str, Any] = {
                "query": query,
                "search_depth": search_depth,
                "topic": topic,
                "max_results": validated_max_results,
                "include_raw_content": include_raw_content,
            }

            if days is not None and topic == "news":
                search_kwargs["days"] = days

            response = self._client.search(**search_kwargs)

            result = self._parse_response(query, response)

            logger.info(
                "Web search completed",
                request_id=request_id,
                result_count=result.result_count,
            )

            if format_output:
                return format_search_result_to_xml(
                    result, include_raw_content=include_raw_content
                )

            return json.dumps(
                [item.model_dump() for item in result.items],
                ensure_ascii=False,
                indent=2,
            )

        except Exception as e:
            logger.error(
                "Web search failed",
                request_id=request_id,
                exception=e,
            )
            raise

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
        """Perform a web search and return as value object.

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
        """
        logger = get_logger(__name__)

        truncated_query = query[:100] + "..." if len(query) > 100 else query
        logger.info(
            "Web search as value object started",
            request_id=request_id,
            query=truncated_query,
        )

        validated_max_results = WebSearchPolicy.validate_max_results(
            max_results or self._max_results
        )

        search_kwargs: dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            "topic": topic,
            "max_results": validated_max_results,
            "include_raw_content": include_raw_content,
        }

        if days is not None and topic == "news":
            search_kwargs["days"] = days

        response = self._client.search(**search_kwargs)

        return self._parse_response(query, response)

    def get_search_context(
        self,
        query: str,
        request_id: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: Literal["general", "news"] = "general",
        max_results: int | None = None,
        max_tokens: int = 4000,
        days: int | None = None,
    ) -> str:
        """Get search context optimized for LLM consumption.

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
        """
        logger = get_logger(__name__)

        truncated_query = query[:100] + "..." if len(query) > 100 else query
        logger.info(
            "Get search context started",
            request_id=request_id,
            query=truncated_query,
            max_tokens=max_tokens,
        )

        validated_max_results = WebSearchPolicy.validate_max_results(
            max_results or self._max_results
        )

        search_kwargs: dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            "topic": topic,
            "max_results": validated_max_results,
            "max_tokens": max_tokens,
        }

        if days is not None and topic == "news":
            search_kwargs["days"] = days

        context = self._client.get_search_context(**search_kwargs)

        logger.info(
            "Get search context completed",
            request_id=request_id,
            context_length=len(context),
        )

        return context

    def _parse_response(self, query: str, response: dict[str, Any]) -> SearchResult:
        """Parse Tavily API response to SearchResult.

        Args:
            query: Original search query.
            response: Raw API response.

        Returns:
            SearchResult value object.
        """
        items = []
        for result in response.get("results", []):
            items.append(
                SearchResultItem(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    content=result.get("content", ""),
                    score=result.get("score", 0.0),
                    raw_content=result.get("raw_content"),
                )
            )

        return SearchResult(query=query, items=items)

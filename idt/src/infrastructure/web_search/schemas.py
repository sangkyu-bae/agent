"""Schemas for web search infrastructure."""

from typing import Literal

from pydantic import BaseModel, Field


class TavilySearchInput(BaseModel):
    """Input schema for Tavily search tool.

    Used as the args_schema for LangChain tool integration.
    """

    query: str = Field(..., description="The search query to execute")
    search_depth: Literal["basic", "advanced"] = Field(
        default="basic",
        description="Search depth: 'basic' for fast, 'advanced' for comprehensive",
    )
    topic: Literal["general", "news"] = Field(
        default="general",
        description="Topic type: 'general' for broad search, 'news' for recent news",
    )
    max_results: int = Field(
        default=3,
        description="Maximum number of results to return (1-10)",
        ge=1,
        le=10,
    )
    include_raw_content: bool = Field(
        default=False,
        description="Whether to include raw page content in results",
    )
    days: int | None = Field(
        default=None,
        description="Number of days to search back (only for 'news' topic)",
        ge=1,
    )

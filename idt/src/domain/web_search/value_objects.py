"""Value objects for web search domain."""

from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """A single search result item.

    Attributes:
        title: Title of the search result.
        url: URL of the search result.
        content: Content snippet from the search result.
        score: Relevance score of the result.
        raw_content: Optional full raw content of the page.
    """

    title: str = Field(..., description="Title of the search result")
    url: str = Field(..., description="URL of the search result")
    content: str = Field(..., description="Content snippet from the search result")
    score: float = Field(..., description="Relevance score of the result")
    raw_content: str | None = Field(
        default=None, description="Optional full raw content of the page"
    )


class SearchResult(BaseModel):
    """Collection of search results.

    Attributes:
        query: The original search query.
        items: List of search result items.
    """

    query: str = Field(..., description="The original search query")
    items: list[SearchResultItem] = Field(
        default_factory=list, description="List of search result items"
    )

    @property
    def result_count(self) -> int:
        """Return the number of search results."""
        return len(self.items)

    @property
    def is_empty(self) -> bool:
        """Check if there are no search results."""
        return len(self.items) == 0

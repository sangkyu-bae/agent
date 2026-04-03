"""Value objects for query rewrite domain."""

from pydantic import BaseModel, Field


class RewrittenQuery(BaseModel):
    """Result of query rewriting.

    Attributes:
        original_query: The original user query before rewriting.
        rewritten_query: The rewritten query optimized for search.
    """

    original_query: str = Field(
        ...,
        description="The original user query before rewriting"
    )
    rewritten_query: str = Field(
        ...,
        description="The rewritten query optimized for vector/web search"
    )

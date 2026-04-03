"""Output schemas for query rewriting."""

from pydantic import BaseModel, Field


class QueryRewriteOutput(BaseModel):
    """Structured output schema for LLM query rewriting.

    Used with ChatOpenAI.with_structured_output() to enforce structured responses.

    Attributes:
        rewritten_query: The rewritten query optimized for search.
    """

    rewritten_query: str = Field(
        ...,
        description="The rewritten query optimized for vector/web search"
    )

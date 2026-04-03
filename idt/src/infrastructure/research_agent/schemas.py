"""Output schemas for research agent."""

from pydantic import BaseModel, Field


class RouterOutput(BaseModel):
    """Structured output schema for LLM question routing.

    Used with ChatOpenAI.with_structured_output() to enforce structured responses.

    Attributes:
        route: The determined route - 'web_search' or 'rag'.
    """

    route: str = Field(
        ...,
        description="The determined route: 'web_search' for current events or 'rag' for document-based queries"
    )


class RelevanceOutput(BaseModel):
    """Structured output schema for LLM relevance evaluation.

    Used with ChatOpenAI.with_structured_output() to enforce structured responses.

    Attributes:
        is_relevant: True if the answer is relevant to the question, False otherwise.
    """

    is_relevant: bool = Field(
        ...,
        description="Whether the answer is relevant to the question"
    )

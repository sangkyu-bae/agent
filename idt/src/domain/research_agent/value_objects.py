"""Value objects for research_agent domain."""

from enum import Enum

from pydantic import BaseModel, Field


class RouteType(str, Enum):
    """Route type for question routing.

    Attributes:
        WEB_SEARCH: Route to web search for current events or real-time info.
        RAG: Route to RAG for document-based queries.
    """

    WEB_SEARCH = "web_search"
    RAG = "rag"


class RouteDecision(BaseModel):
    """Decision result for question routing.

    Attributes:
        route: The chosen route type.
        reason: Explanation for the routing decision.
    """

    route: RouteType = Field(..., description="The chosen route type")
    reason: str = Field(..., description="Explanation for the routing decision")


class RelevanceResult(BaseModel):
    """Result of answer relevance evaluation.

    Attributes:
        is_relevant: True if the answer is relevant to the question,
                     False otherwise.
    """

    is_relevant: bool = Field(
        ..., description="Whether the answer is relevant to the question"
    )

"""Research agent state definition for LangGraph workflow."""

from typing import Any, List, Optional

from typing_extensions import TypedDict

from src.domain.research_agent.value_objects import RouteType


class ResearchState(TypedDict):
    """State for Self-Corrective RAG workflow.

    This TypedDict defines the state passed between LangGraph nodes.

    Input Fields:
        question: The user's question to answer.
        request_id: Unique request identifier for logging.

    Routing Fields:
        route: Determined route (web_search or rag).
        route_reason: Explanation for the routing decision.

    Retrieval Fields:
        documents: List of retrieved documents.
        web_search_results: Results from web search (if used).

    Generation Fields:
        generation: The generated answer.

    Evaluation Fields:
        is_hallucinated: Whether the generation is hallucinated.
        is_relevant: Whether the answer is relevant to the question.

    Control Fields:
        retry_count: Number of retries performed.
        transformed_query: Rewritten query for retry.

    Metadata Fields:
        errors: List of error messages.
        status: Current workflow status.
    """

    # Input
    question: str
    request_id: str

    # Routing
    route: Optional[RouteType]
    route_reason: Optional[str]

    # Retrieval
    documents: List[Any]  # List[Document] from langchain
    web_search_results: Optional[List[Any]]

    # Generation
    generation: Optional[str]

    # Evaluation
    is_hallucinated: Optional[bool]
    is_relevant: Optional[bool]

    # Control
    retry_count: int
    transformed_query: Optional[str]

    # Metadata
    errors: List[str]
    status: str  # routing, retrieving, generating, evaluating, completed, failed

"""Self-Corrective RAG Workflow using LangGraph."""

from typing import Any, Callable, Optional

from langgraph.graph import StateGraph, END

from src.domain.research_agent.policy import RoutingPolicy
from src.domain.research_agent.state import ResearchState
from src.domain.research_agent.value_objects import RouteType
from src.infrastructure.logging import get_logger
from src.infrastructure.research_agent.generator_adapter import GeneratorAdapter
from src.infrastructure.research_agent.relevance_adapter import RelevanceEvaluatorAdapter
from src.infrastructure.research_agent.router_adapter import RouterAdapter
from src.application.hallucination.use_case import HallucinationEvaluatorUseCase
from src.application.query_rewrite.use_case import QueryRewriterUseCase
from src.application.web_search.use_case import WebSearchUseCase


def create_initial_state(question: str, request_id: str) -> ResearchState:
    """Create initial research state.

    Args:
        question: The user's question.
        request_id: Request ID for logging.

    Returns:
        Initial ResearchState.
    """
    return {
        "question": question,
        "request_id": request_id,
        "route": None,
        "route_reason": None,
        "documents": [],
        "web_search_results": None,
        "generation": None,
        "is_hallucinated": None,
        "is_relevant": None,
        "retry_count": 0,
        "transformed_query": None,
        "errors": [],
        "status": "routing",
    }


class SelfCorrectiveRAGWorkflow:
    """Self-Corrective RAG workflow using LangGraph.

    This workflow:
    1. Routes questions to web search or RAG
    2. Retrieves relevant documents (TODO: use retriever when implemented)
    3. Generates answers based on context
    4. Checks for hallucination
    5. Checks answer relevance
    6. Retries with rewritten query if needed
    """

    def __init__(
        self,
        router_adapter: RouterAdapter,
        generator_adapter: GeneratorAdapter,
        relevance_evaluator_adapter: RelevanceEvaluatorAdapter,
        hallucination_use_case: HallucinationEvaluatorUseCase,
        query_rewriter_use_case: QueryRewriterUseCase,
        web_search_use_case: WebSearchUseCase,
        retriever: Optional[Callable[[str, str], list[str]]] = None,
    ) -> None:
        """Initialize the workflow.

        Args:
            router_adapter: Adapter for routing questions.
            generator_adapter: Adapter for generating answers.
            relevance_evaluator_adapter: Adapter for evaluating answer relevance.
            hallucination_use_case: Use case for hallucination evaluation.
            query_rewriter_use_case: Use case for query rewriting.
            web_search_use_case: Use case for web search.
            retriever: Optional callable (question, request_id) -> list[str] for RAG.
                       When None, returns empty documents (TODO: integrate RET-001).
        """
        self._logger = get_logger(__name__)
        self._router = router_adapter
        self._generator = generator_adapter
        self._relevance_evaluator = relevance_evaluator_adapter
        self._hallucination_uc = hallucination_use_case
        self._query_rewriter_uc = query_rewriter_use_case
        self._web_search_uc = web_search_use_case
        self._retriever = retriever
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Build the LangGraph workflow."""
        workflow = StateGraph(ResearchState)

        # Add nodes
        workflow.add_node("route_question", self._route_question_node)
        workflow.add_node("web_search", self._web_search_node)
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("check_hallucination", self._check_hallucination_node)
        workflow.add_node("check_relevance", self._check_relevance_node)
        workflow.add_node("transform_query", self._transform_query_node)

        # Set entry point
        workflow.set_entry_point("route_question")

        # Add edges from route_question
        workflow.add_conditional_edges(
            "route_question",
            self._route_decision,
            {
                "web_search": "web_search",
                "rag": "retrieve",
            },
        )

        # Web search leads to generate
        workflow.add_edge("web_search", "generate")

        # Retrieve leads to generate
        workflow.add_edge("retrieve", "generate")

        # Generate leads to hallucination check
        workflow.add_edge("generate", "check_hallucination")

        # Hallucination check leads to relevance check or retry
        workflow.add_conditional_edges(
            "check_hallucination",
            self._after_hallucination_check,
            {
                "continue": "check_relevance",
                "retry": "transform_query",
                "end": END,
            },
        )

        # Relevance check leads to end or retry
        workflow.add_conditional_edges(
            "check_relevance",
            self._after_relevance_check,
            {
                "end": END,
                "retry": "transform_query",
            },
        )

        # Transform query leads back to route
        workflow.add_edge("transform_query", "route_question")

        return workflow.compile()

    async def _route_question_node(self, state: ResearchState) -> ResearchState:
        """Route question to web search or RAG."""
        request_id = state["request_id"]
        question = state.get("transformed_query") or state["question"]

        self._logger.info(
            "Routing question",
            request_id=request_id,
            question_preview=question[:50]
        )

        # First check domain policy for keywords
        if RoutingPolicy.should_use_web_search(question):
            return {
                **state,
                "route": RouteType.WEB_SEARCH,
                "route_reason": "Keyword-based routing to web search",
                "status": "routing",
            }

        # Use LLM router for more nuanced decision
        route_decision = await self._router.route(question=question, request_id=request_id)

        return {
            **state,
            "route": route_decision.route,
            "route_reason": route_decision.reason,
            "status": "routing",
        }

    async def _web_search_node(self, state: ResearchState) -> ResearchState:
        """Perform web search."""
        request_id = state["request_id"]
        question = state.get("transformed_query") or state["question"]

        self._logger.info(
            "Performing web search",
            request_id=request_id
        )

        context = self._web_search_uc.get_context(
            query=question,
            request_id=request_id,
        )

        return {
            **state,
            "documents": [context],
            "web_search_results": [context],
            "status": "retrieving",
        }

    async def _retrieve_node(self, state: ResearchState) -> ResearchState:
        """Retrieve documents from RAG.

        Uses the injected retriever if available, otherwise returns empty documents.
        TODO: Integrate with RET-001 retriever when implemented.
        """
        request_id = state["request_id"]
        question = state.get("transformed_query") or state["question"]

        self._logger.info(
            "Retrieving documents",
            request_id=request_id
        )

        if self._retriever is not None:
            documents = self._retriever(question, request_id)
        else:
            # TODO: Replace with actual retriever call when RET-001 is implemented
            documents = []

        return {
            **state,
            "documents": documents,
            "status": "retrieving",
        }

    async def _generate_node(self, state: ResearchState) -> ResearchState:
        """Generate answer based on context."""
        request_id = state["request_id"]
        question = state.get("transformed_query") or state["question"]
        documents = state["documents"]

        self._logger.info(
            "Generating answer",
            request_id=request_id,
            document_count=len(documents)
        )

        context = "\n\n---\n\n".join(documents) if documents else "No context available."

        generation = await self._generator.generate(
            question=question,
            context=context,
            request_id=request_id,
        )

        return {
            **state,
            "generation": generation,
            "status": "generating",
        }

    async def _check_hallucination_node(self, state: ResearchState) -> ResearchState:
        """Check for hallucination in generated answer."""
        request_id = state["request_id"]
        documents = state["documents"]
        generation = state["generation"]

        self._logger.info(
            "Checking hallucination",
            request_id=request_id
        )

        # Skip hallucination check if no documents (can't verify)
        if not documents or not generation:
            return {
                **state,
                "is_hallucinated": False,
                "status": "evaluating",
            }

        result = await self._hallucination_uc.evaluate(
            documents=documents,
            generation=generation,
            request_id=request_id,
        )

        return {
            **state,
            "is_hallucinated": result.is_hallucinated,
            "status": "evaluating",
        }

    async def _check_relevance_node(self, state: ResearchState) -> ResearchState:
        """Check answer relevance."""
        request_id = state["request_id"]
        question = state.get("transformed_query") or state["question"]
        generation = state["generation"]

        self._logger.info(
            "Checking relevance",
            request_id=request_id
        )

        result = await self._relevance_evaluator.evaluate(
            question=question,
            answer=generation,
            request_id=request_id,
        )

        return {
            **state,
            "is_relevant": result.is_relevant,
            "status": "evaluating",
        }

    async def _transform_query_node(self, state: ResearchState) -> ResearchState:
        """Transform/rewrite query for retry."""
        request_id = state["request_id"]
        question = state.get("transformed_query") or state["question"]
        retry_count = state["retry_count"]

        self._logger.info(
            "Transforming query",
            request_id=request_id,
            retry_count=retry_count
        )

        result = await self._query_rewriter_uc.rewrite(
            query=question,
            request_id=request_id,
        )

        return {
            **state,
            "transformed_query": result.rewritten_query,
            "retry_count": retry_count + 1,
            "status": "routing",
        }

    def _route_decision(self, state: ResearchState) -> str:
        """Determine next step after routing."""
        route = state.get("route")
        if route == RouteType.WEB_SEARCH:
            return "web_search"
        return "rag"

    def _after_hallucination_check(self, state: ResearchState) -> str:
        """Determine next step after hallucination check."""
        is_hallucinated = state.get("is_hallucinated", False)
        retry_count = state["retry_count"]

        if not is_hallucinated:
            return "continue"

        if not RoutingPolicy.can_retry(retry_count):
            return "end"

        return "retry"

    def _after_relevance_check(self, state: ResearchState) -> str:
        """Determine next step after relevance check."""
        is_relevant = state.get("is_relevant", True)
        is_hallucinated = state.get("is_hallucinated", False)
        retry_count = state["retry_count"]

        if RoutingPolicy.should_end(is_relevant, is_hallucinated, retry_count):
            return "end"

        return "retry"

    async def run(self, question: str, request_id: str) -> ResearchState:
        """Run the Self-Corrective RAG workflow.

        Args:
            question: The user's question.
            request_id: Request ID for logging.

        Returns:
            Final ResearchState with answer and metadata.
        """
        self._logger.info(
            "Starting Self-Corrective RAG workflow",
            request_id=request_id,
            question_preview=question[:50]
        )

        initial_state = create_initial_state(question=question, request_id=request_id)

        try:
            result = await self._graph.ainvoke(initial_state)
            result["status"] = "completed"

            self._logger.info(
                "Workflow completed",
                request_id=request_id,
                retry_count=result["retry_count"]
            )

            return result

        except Exception as e:
            self._logger.error(
                "Workflow failed",
                exception=e,
                request_id=request_id
            )

            return {
                **initial_state,
                "status": "failed",
                "errors": [str(e)],
            }

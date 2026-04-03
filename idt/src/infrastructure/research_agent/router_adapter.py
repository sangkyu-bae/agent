"""Adapter for question routing using LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.domain.research_agent.value_objects import RouteDecision, RouteType
from src.infrastructure.research_agent.prompts import (
    ROUTER_SYSTEM_PROMPT,
    ROUTER_HUMAN_TEMPLATE,
)
from src.infrastructure.research_agent.schemas import RouterOutput
from src.infrastructure.logging import get_logger


class RouterAdapter:
    """Adapter for routing questions to web_search or RAG using LLM.

    Uses ChatOpenAI with structured output to determine the appropriate
    route for a given question.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0
    ) -> None:
        """Initialize the router adapter.

        Args:
            model_name: The OpenAI model to use for routing.
            temperature: Temperature setting for the LLM (0.0 for deterministic output).
        """
        self._logger = get_logger(__name__)
        self._llm = ChatOpenAI(model=model_name, temperature=temperature)
        self._chain = self._build_chain()

    def _build_chain(self):
        """Build the LangChain chain for question routing."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", ROUTER_SYSTEM_PROMPT),
            ("human", ROUTER_HUMAN_TEMPLATE),
        ])
        return prompt | self._llm.with_structured_output(RouterOutput)

    async def route(
        self,
        question: str,
        request_id: str
    ) -> RouteDecision:
        """Route a question to web_search or RAG.

        Args:
            question: The user's question to route.
            request_id: Request ID for logging context.

        Returns:
            RouteDecision with route type and reason.

        Raises:
            Exception: If LLM API call fails.
        """
        self._logger.info(
            "Routing question",
            request_id=request_id,
            question_length=len(question)
        )

        try:
            output: RouterOutput = await self._chain.ainvoke({
                "question": question,
            })

            route_type = (
                RouteType.WEB_SEARCH
                if output.route == "web_search"
                else RouteType.RAG
            )

            reason = (
                f"Routed to {output.route} based on question analysis"
            )

            self._logger.info(
                "Question routed",
                request_id=request_id,
                route=output.route
            )

            return RouteDecision(route=route_type, reason=reason)

        except Exception as e:
            self._logger.error(
                "Question routing failed",
                exception=e,
                request_id=request_id
            )
            raise

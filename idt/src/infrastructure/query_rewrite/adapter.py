"""Adapter for query rewriting using LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.domain.query_rewrite.value_objects import RewrittenQuery
from src.infrastructure.query_rewrite.prompts import (
    QUERY_REWRITE_SYSTEM_PROMPT,
    QUERY_REWRITE_HUMAN_TEMPLATE,
)
from src.infrastructure.query_rewrite.schemas import QueryRewriteOutput
from src.infrastructure.logging import get_logger


class QueryRewriterAdapter:
    """Adapter for rewriting queries using LLM with structured output.

    Uses ChatOpenAI with structured output to transform user queries
    into search-optimized queries.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0
    ) -> None:
        """Initialize the query rewriter adapter.

        Args:
            model_name: The OpenAI model to use for rewriting.
            temperature: Temperature setting for the LLM (0.0 for deterministic output).
        """
        self._logger = get_logger(__name__)
        self._llm = ChatOpenAI(model=model_name, temperature=temperature)
        self._chain = self._build_chain()

    def _build_chain(self):
        """Build the LangChain chain for query rewriting."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", QUERY_REWRITE_SYSTEM_PROMPT),
            ("human", QUERY_REWRITE_HUMAN_TEMPLATE),
        ])
        return prompt | self._llm.with_structured_output(QueryRewriteOutput)

    async def rewrite(
        self,
        query: str,
        request_id: str
    ) -> RewrittenQuery:
        """Rewrite a query for better search results.

        Args:
            query: The original user query to rewrite.
            request_id: Request ID for logging context.

        Returns:
            RewrittenQuery with original_query and rewritten_query fields.

        Raises:
            Exception: If LLM API call fails.
        """
        self._logger.info(
            "Query rewrite started",
            request_id=request_id,
            query_length=len(query)
        )

        try:
            output: QueryRewriteOutput = await self._chain.ainvoke({
                "query": query,
            })

            self._logger.info(
                "Query rewrite completed",
                request_id=request_id,
                rewritten_length=len(output.rewritten_query)
            )

            return RewrittenQuery(
                original_query=query,
                rewritten_query=output.rewritten_query
            )
        except Exception as e:
            self._logger.error(
                "Query rewrite failed",
                exception=e,
                request_id=request_id
            )
            raise

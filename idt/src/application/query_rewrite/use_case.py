"""Use case for query rewriting."""

from src.domain.query_rewrite.policy import QueryRewritePolicy
from src.domain.query_rewrite.value_objects import RewrittenQuery
from src.infrastructure.query_rewrite.adapter import QueryRewriterAdapter


class QueryRewriterUseCase:
    """Use case for rewriting user queries.

    Orchestrates the query rewriting process by:
    1. Validating input using QueryRewritePolicy
    2. Delegating to QueryRewriterAdapter for LLM rewriting
    3. Validating the rewritten result
    """

    def __init__(self, rewriter_adapter: QueryRewriterAdapter) -> None:
        """Initialize the use case.

        Args:
            rewriter_adapter: Adapter for performing query rewriting.
        """
        self._rewriter = rewriter_adapter

    async def rewrite(
        self,
        query: str,
        request_id: str
    ) -> RewrittenQuery:
        """Rewrite a user query for better search results.

        Args:
            query: The original user query to rewrite.
            request_id: Request ID for logging context.

        Returns:
            RewrittenQuery with original_query and rewritten_query fields.

        Raises:
            ValueError: If query is empty, too short, or too long.
            RuntimeError: If rewritten result is invalid.
        """
        stripped_query = query.strip() if query else ""

        if not stripped_query:
            raise ValueError("Query is required")

        if len(stripped_query) < QueryRewritePolicy.MIN_QUERY_LENGTH:
            raise ValueError("Query is too short")

        if len(stripped_query) > QueryRewritePolicy.MAX_QUERY_LENGTH:
            raise ValueError("Query is too long")

        result = await self._rewriter.rewrite(
            query=stripped_query,
            request_id=request_id
        )

        if not QueryRewritePolicy.validate_rewritten_query(result.rewritten_query):
            raise RuntimeError("Rewritten query is invalid")

        return result

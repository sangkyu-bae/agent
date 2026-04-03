"""Domain policy for web search operations."""


class WebSearchPolicy:
    """Policy rules for web search validation.

    Defines constants and validation rules for web search queries.
    """

    MIN_QUERY_LENGTH = 5
    MAX_QUERY_LENGTH = 500
    DEFAULT_MAX_RESULTS = 3
    MAX_RESULTS_LIMIT = 10

    @staticmethod
    def validate_query(query: str | None) -> bool:
        """Validate a search query.

        Args:
            query: The search query to validate.

        Returns:
            True if the query is valid, False otherwise.
        """
        if query is None:
            return False

        stripped_query = query.strip()

        if not stripped_query:
            return False

        if len(stripped_query) < WebSearchPolicy.MIN_QUERY_LENGTH:
            return False

        if len(stripped_query) > WebSearchPolicy.MAX_QUERY_LENGTH:
            return False

        return True

    @staticmethod
    def validate_max_results(max_results: int | None) -> int:
        """Validate and normalize max_results value.

        Args:
            max_results: The requested maximum number of results.

        Returns:
            Validated max_results value within acceptable bounds.
        """
        if max_results is None or max_results < 1:
            return WebSearchPolicy.DEFAULT_MAX_RESULTS

        if max_results > WebSearchPolicy.MAX_RESULTS_LIMIT:
            return WebSearchPolicy.MAX_RESULTS_LIMIT

        return max_results

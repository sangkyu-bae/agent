"""Domain policy for query rewriting."""


class QueryRewritePolicy:
    """Policy rules for query rewriting.

    Defines when query rewriting is needed and validates rewritten queries.
    """

    MIN_QUERY_LENGTH = 2
    MAX_QUERY_LENGTH = 1000
    MIN_WELL_FORMED_LENGTH = 15

    AMBIGUOUS_PATTERNS = [
        "이거", "그거", "저거", "그것", "이것", "저것",
        "뭐야", "뭐", "어떻게",
    ]

    @staticmethod
    def requires_rewrite(query: str) -> bool:
        """Determine if a query requires rewriting.

        A query requires rewriting when:
        - It is too short (less than MIN_WELL_FORMED_LENGTH characters)
        - It contains ambiguous pronouns or patterns
        - It lacks sufficient context for effective retrieval

        Args:
            query: The user's original query.

        Returns:
            True if rewriting is recommended, False otherwise.
        """
        if not query or not query.strip():
            return False

        stripped_query = query.strip()

        if len(stripped_query) < QueryRewritePolicy.MIN_WELL_FORMED_LENGTH:
            return True

        for pattern in QueryRewritePolicy.AMBIGUOUS_PATTERNS:
            if pattern in stripped_query:
                return True

        return False

    @staticmethod
    def validate_rewritten_query(rewritten: str) -> bool:
        """Validate a rewritten query.

        Args:
            rewritten: The rewritten query to validate.

        Returns:
            True if the rewritten query is valid, False otherwise.
        """
        if not rewritten or not rewritten.strip():
            return False

        stripped = rewritten.strip()

        if len(stripped) < QueryRewritePolicy.MIN_QUERY_LENGTH:
            return False

        if len(stripped) > QueryRewritePolicy.MAX_QUERY_LENGTH:
            return False

        return True

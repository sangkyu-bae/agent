"""Domain policies for retrieval.

Business rules for query validation and retrieval constraints.
"""


class RetrievalPolicy:
    """Defines constraints and validation rules for retrieval operations."""

    MIN_QUERY_LENGTH: int = 2
    MAX_QUERY_LENGTH: int = 1000
    MAX_TOP_K: int = 50
    DEFAULT_TOP_K: int = 10

    @classmethod
    def validate_query(cls, query: str) -> None:
        """Validate retrieval query against policy constraints.

        Args:
            query: The query string to validate.

        Raises:
            ValueError: If query violates policy constraints.
        """
        stripped = query.strip() if query else ""
        if not stripped:
            raise ValueError("Query is required")
        if len(stripped) < cls.MIN_QUERY_LENGTH:
            raise ValueError(
                f"Query must be at least {cls.MIN_QUERY_LENGTH} characters"
            )
        if len(stripped) > cls.MAX_QUERY_LENGTH:
            raise ValueError(
                f"Query must be at most {cls.MAX_QUERY_LENGTH} characters"
            )

    @classmethod
    def clamp_top_k(cls, top_k: int) -> int:
        """Clamp top_k to allowed range.

        Args:
            top_k: Requested number of results.

        Returns:
            Clamped value within [1, MAX_TOP_K].
        """
        return max(1, min(top_k, cls.MAX_TOP_K))

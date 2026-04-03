"""Domain policy for research agent routing."""


class RoutingPolicy:
    """Policy rules for question routing and retry logic.

    Defines constants and validation rules for routing questions
    to web search or RAG, and managing retry behavior.
    """

    MAX_RETRY_COUNT = 3

    WEB_SEARCH_KEYWORDS = [
        "최신",
        "현재",
        "오늘",
        "최근",
        "뉴스",
        "실시간",
        "지금",
        "이번",
        "today",
        "current",
        "latest",
        "recent",
        "news",
        "real-time",
    ]

    @staticmethod
    def should_use_web_search(question: str | None) -> bool:
        """Determine if web search should be used based on keywords.

        Args:
            question: The user's question.

        Returns:
            True if the question contains web search keywords, False otherwise.
        """
        if question is None:
            return False

        stripped = question.strip()
        if not stripped:
            return False

        lower_question = stripped.lower()
        return any(
            keyword.lower() in lower_question
            for keyword in RoutingPolicy.WEB_SEARCH_KEYWORDS
        )

    @staticmethod
    def can_retry(retry_count: int) -> bool:
        """Determine if retry is allowed based on current retry count.

        Args:
            retry_count: The current number of retries performed.

        Returns:
            True if retry is allowed, False otherwise.
        """
        return retry_count < RoutingPolicy.MAX_RETRY_COUNT

    @staticmethod
    def should_end(is_relevant: bool, is_hallucinated: bool, retry_count: int) -> bool:
        """Determine if the workflow should end.

        The workflow should end when:
        - The answer is relevant AND not hallucinated (success)
        - OR max retry count has been reached (give up)

        Args:
            is_relevant: Whether the answer is relevant to the question.
            is_hallucinated: Whether the answer is hallucinated.
            retry_count: The current number of retries performed.

        Returns:
            True if the workflow should end, False otherwise.
        """
        if retry_count >= RoutingPolicy.MAX_RETRY_COUNT:
            return True

        if is_relevant and not is_hallucinated:
            return True

        return False

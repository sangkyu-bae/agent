"""CompressorConfig value object for document compressor configuration."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CompressorConfig:
    """Configuration for document compression.

    Attributes:
        relevance_threshold: Minimum score for document to be considered relevant.
        max_concurrency: Maximum number of concurrent LLM calls (Semaphore limit).
        timeout_seconds: Timeout for each LLM call.
        include_reasoning: Whether to include reasoning in results.
        retry_count: Number of retries on failure.
    """

    relevance_threshold: float = 0.5
    max_concurrency: int = 10
    timeout_seconds: float = 30.0
    include_reasoning: bool = True
    retry_count: int = 3

    def __post_init__(self) -> None:
        """Validate the configuration after initialization."""
        self._validate_relevance_threshold()
        self._validate_max_concurrency()
        self._validate_timeout_seconds()
        self._validate_retry_count()

    def _validate_relevance_threshold(self) -> None:
        if self.relevance_threshold < 0.0 or self.relevance_threshold > 1.0:
            raise ValueError("relevance_threshold must be between 0.0 and 1.0")

    def _validate_max_concurrency(self) -> None:
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than 0")

    def _validate_timeout_seconds(self) -> None:
        if self.timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be greater than 0")

    def _validate_retry_count(self) -> None:
        if self.retry_count < 0:
            raise ValueError("retry_count must be 0 or greater")

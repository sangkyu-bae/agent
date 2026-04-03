"""RelevanceResult value object for document relevance evaluation."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RelevanceResult:
    """Result of document relevance evaluation.

    Attributes:
        is_relevant: Whether the document is relevant to the query.
        score: Relevance score between 0.0 and 1.0.
        reasoning: Optional explanation of the relevance decision.
    """

    is_relevant: bool
    score: float
    reasoning: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate the result after initialization."""
        self._validate_score()

    def _validate_score(self) -> None:
        if self.score < 0.0 or self.score > 1.0:
            raise ValueError("score must be between 0.0 and 1.0")

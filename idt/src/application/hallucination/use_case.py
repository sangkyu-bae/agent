"""Use case for hallucination evaluation."""

from src.domain.hallucination.policy import HallucinationPolicy
from src.domain.hallucination.value_objects import HallucinationEvaluationResult
from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter


class HallucinationEvaluatorUseCase:
    """Use case for evaluating hallucination in LLM generations.

    Orchestrates the hallucination evaluation process by:
    1. Validating input using HallucinationPolicy
    2. Delegating to HallucinationEvaluatorAdapter for LLM evaluation
    """

    def __init__(self, evaluator_adapter: HallucinationEvaluatorAdapter) -> None:
        """Initialize the use case.

        Args:
            evaluator_adapter: Adapter for performing hallucination evaluation.
        """
        self._evaluator = evaluator_adapter

    async def evaluate(
        self,
        documents: list[str],
        generation: str | None,
        request_id: str
    ) -> HallucinationEvaluationResult:
        """Evaluate if a generation is hallucinated.

        Args:
            documents: List of reference documents to check against.
            generation: The LLM-generated text to evaluate.
            request_id: Request ID for logging context.

        Returns:
            HallucinationEvaluationResult with is_hallucinated field.

        Raises:
            ValueError: If generation or documents are invalid.
        """
        if not HallucinationPolicy.requires_evaluation(generation, documents):
            raise ValueError("Generation and documents are required")

        return await self._evaluator.evaluate(
            documents=documents,
            generation=generation,
            request_id=request_id
        )

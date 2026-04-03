"""Domain policy for hallucination evaluation."""


class HallucinationPolicy:
    """Policy rules for hallucination evaluation."""

    @staticmethod
    def requires_evaluation(generation: str | None, documents: list[str]) -> bool:
        """Determine if hallucination evaluation is required.

        Evaluation is required when:
        - generation is a non-empty, non-whitespace string
        - documents list contains at least one non-empty, non-whitespace document

        Args:
            generation: The LLM-generated answer to evaluate.
            documents: List of reference documents.

        Returns:
            True if evaluation should proceed, False otherwise.
        """
        if generation is None:
            return False

        if not generation.strip():
            return False

        if not documents:
            return False

        has_valid_document = any(doc.strip() for doc in documents)
        if not has_valid_document:
            return False

        return True

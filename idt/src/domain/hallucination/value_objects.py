"""Value objects for hallucination evaluation domain."""

from pydantic import BaseModel, Field


class HallucinationEvaluationResult(BaseModel):
    """Result of hallucination evaluation.

    Attributes:
        is_hallucinated: True if the generation is hallucinated (not grounded in documents),
                         False if the generation is factually grounded.
    """

    is_hallucinated: bool = Field(
        ...,
        description="Whether the generation is hallucinated (not grounded in provided documents)"
    )

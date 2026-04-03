"""Output schemas for hallucination evaluation."""

from pydantic import BaseModel, Field


class HallucinationOutput(BaseModel):
    """Structured output schema for LLM hallucination evaluation.

    Used with ChatOpenAI.with_structured_output() to enforce structured responses.

    Attributes:
        is_hallucinated: True if the LLM generation is hallucinated (not grounded in documents),
                         False if grounded.
    """

    is_hallucinated: bool = Field(
        ...,
        description="Whether the LLM generation is hallucinated (not grounded in provided documents)"
    )

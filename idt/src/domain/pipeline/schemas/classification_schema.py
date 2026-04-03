"""Classification schema for document category classification."""
from pydantic import BaseModel, Field

from src.domain.pipeline.enums.document_category import DocumentCategory


class ClassificationResult(BaseModel):
    """Result of document classification.

    Attributes:
        category: Classified document category.
        confidence: Confidence score between 0.0 and 1.0.
        reasoning: Reasoning for the classification decision.
    """

    category: DocumentCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

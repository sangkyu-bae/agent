"""Classify node for document processing pipeline."""
from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.pipeline.schemas.classification_schema import ClassificationResult
from src.domain.pipeline.state.pipeline_state import PipelineState
from src.infrastructure.pipeline.prompts.classification_prompt import (
    extract_sample_pages,
    build_classification_prompt,
    CLASSIFICATION_SYSTEM_PROMPT,
)


CONFIDENCE_THRESHOLD = 0.5


async def classify_node(
    state: PipelineState,
    llm_provider: LLMProviderInterface,
) -> PipelineState:
    """Classify document category using LLM.

    Uses sample pages from parsed documents to determine category.
    Falls back to GENERAL if confidence is below threshold.

    Args:
        state: Current pipeline state with parsed_documents.
        llm_provider: LLM provider for classification.

    Returns:
        Updated pipeline state with category information.
    """
    try:
        documents = state.get("parsed_documents", [])

        if not documents:
            return {
                **state,
                "status": "failed",
                "errors": state["errors"] + ["No documents to classify"],
            }

        # Extract sample pages
        sample_pages = extract_sample_pages(documents)

        # Build prompt and classify
        prompt = build_classification_prompt(sample_pages)
        full_prompt = f"{CLASSIFICATION_SYSTEM_PROMPT}\n\n{prompt}"

        classification: ClassificationResult = await llm_provider.generate_structured(
            full_prompt, ClassificationResult
        )

        # Apply confidence threshold fallback
        category = classification.category
        if classification.confidence < CONFIDENCE_THRESHOLD:
            category = DocumentCategory.GENERAL

        return {
            **state,
            "category": category,
            "category_confidence": classification.confidence,
            "classification_reasoning": classification.reasoning,
            "sample_pages": sample_pages,
            "status": "classifying",
        }

    except Exception as e:
        return {
            **state,
            "status": "failed",
            "errors": state["errors"] + [f"Classification failed: {str(e)}"],
        }

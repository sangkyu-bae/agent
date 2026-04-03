"""Relevance prompt templates for document compression."""
from pydantic import BaseModel, Field

from langchain_core.documents import Document


class RelevanceResponse(BaseModel):
    """Schema for LLM relevance evaluation response."""

    is_relevant: bool = Field(description="Whether the document is relevant to query")
    score: float = Field(ge=0.0, le=1.0, description="Relevance score from 0.0 to 1.0")
    reasoning: str = Field(description="Explanation for the relevance decision")


class RelevancePromptBuilder:
    """Builder for relevance evaluation prompts."""

    _PROMPT_TEMPLATE_WITH_REASONING = """You are a document relevance evaluator. Evaluate whether the given document is relevant to the query.

Query: {query}

Document Content:
{content}

Evaluate the document's relevance to the query and respond with JSON containing:
- is_relevant: true if the document helps answer the query, false otherwise
- score: a relevance score from 0.0 (completely irrelevant) to 1.0 (highly relevant)
- reasoning: a brief explanation of why the document is or is not relevant

Respond only with valid JSON."""

    _PROMPT_TEMPLATE_WITHOUT_REASONING = """You are a document relevance evaluator. Evaluate whether the given document is relevant to the query.

Query: {query}

Document Content:
{content}

Evaluate the document's relevance to the query and respond with JSON containing:
- is_relevant: true if the document helps answer the query, false otherwise
- score: a relevance score from 0.0 (completely irrelevant) to 1.0 (highly relevant)
- reasoning: a brief note (can be minimal)

Respond only with valid JSON."""

    def build_prompt(
        self,
        document: Document,
        query: str,
        include_reasoning: bool = True,
    ) -> str:
        """Build a relevance evaluation prompt.

        Args:
            document: The document to evaluate.
            query: The query to evaluate against.
            include_reasoning: Whether to request detailed reasoning.

        Returns:
            The formatted prompt string.
        """
        template = (
            self._PROMPT_TEMPLATE_WITH_REASONING
            if include_reasoning
            else self._PROMPT_TEMPLATE_WITHOUT_REASONING
        )

        return template.format(
            query=query,
            content=document.page_content,
        )

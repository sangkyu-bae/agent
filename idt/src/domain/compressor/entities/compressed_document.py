"""CompressedDocument entity for storing document with relevance evaluation."""
from dataclasses import dataclass
from typing import Any, Dict, Optional

from langchain_core.documents import Document

from src.domain.compressor.value_objects.relevance_result import RelevanceResult


@dataclass(frozen=True)
class CompressedDocument:
    """A document with its relevance evaluation result.

    Attributes:
        document: The original LangChain Document.
        relevance: The relevance evaluation result.
    """

    document: Document
    relevance: RelevanceResult

    @property
    def is_relevant(self) -> bool:
        """Whether the document is relevant to the query."""
        return self.relevance.is_relevant

    @property
    def score(self) -> float:
        """The relevance score."""
        return self.relevance.score

    @property
    def reasoning(self) -> Optional[str]:
        """The reasoning for the relevance decision."""
        return self.relevance.reasoning

    @property
    def page_content(self) -> str:
        """The document's page content."""
        return self.document.page_content

    @property
    def metadata(self) -> Dict[str, Any]:
        """The document's metadata."""
        return self.document.metadata

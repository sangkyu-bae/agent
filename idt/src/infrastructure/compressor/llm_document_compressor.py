"""LLM-based document compressor with parallel processing support."""
import asyncio
from typing import List

from langchain_core.documents import Document

from src.domain.compressor.interfaces.document_compressor_interface import (
    DocumentCompressorInterface,
)
from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.domain.compressor.entities.compressed_document import CompressedDocument
from src.domain.compressor.value_objects.compressor_config import CompressorConfig
from src.domain.compressor.value_objects.relevance_result import RelevanceResult
from src.infrastructure.compressor.prompts.relevance_prompt import (
    RelevancePromptBuilder,
    RelevanceResponse,
)
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class LLMDocumentCompressor(DocumentCompressorInterface):
    """LLM-based document compressor with parallel processing."""

    def __init__(
        self,
        llm_provider: LLMProviderInterface,
        config: CompressorConfig,
    ) -> None:
        self._llm = llm_provider
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._prompt_builder = RelevancePromptBuilder()

    async def compress(
        self, documents: List[Document], query: str
    ) -> List[Document]:
        """Compress/filter documents based on relevance to query."""
        if not documents:
            return []

        compressed = await self.compress_with_scores(documents, query)
        return [
            doc.document
            for doc in compressed
            if doc.score >= self._config.relevance_threshold
        ]

    async def compress_with_scores(
        self, documents: List[Document], query: str
    ) -> List[CompressedDocument]:
        """Compress documents and return with relevance scores."""
        if not documents:
            return []

        tasks = [self._evaluate_with_semaphore(doc, query) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        compressed_docs = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                logger.error(
                    "Document evaluation failed",
                    exception=result,
                    doc_length=len(doc.page_content),
                )
                continue
            compressed_docs.append(result)

        return compressed_docs

    async def _evaluate_with_semaphore(
        self, document: Document, query: str
    ) -> CompressedDocument:
        async with self._semaphore:
            return await self._evaluate_relevance(document, query)

    async def _evaluate_relevance(
        self, document: Document, query: str
    ) -> CompressedDocument:
        prompt = self._prompt_builder.build_prompt(
            document, query, include_reasoning=self._config.include_reasoning
        )

        response: RelevanceResponse = await self._llm.generate_structured(
            prompt, RelevanceResponse
        )

        relevance = RelevanceResult(
            is_relevant=response.is_relevant,
            score=response.score,
            reasoning=response.reasoning,
        )

        return CompressedDocument(document=document, relevance=relevance)

    def get_compressor_name(self) -> str:
        return "llm-document-compressor"

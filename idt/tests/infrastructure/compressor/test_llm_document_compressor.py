"""Tests for LLMDocumentCompressor with parallel processing."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from langchain_core.documents import Document

from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.domain.compressor.interfaces.document_compressor_interface import (
    DocumentCompressorInterface,
)
from src.domain.compressor.value_objects.compressor_config import CompressorConfig
from src.domain.compressor.entities.compressed_document import CompressedDocument
from src.infrastructure.compressor.llm_document_compressor import LLMDocumentCompressor
from src.infrastructure.compressor.prompts.relevance_prompt import RelevanceResponse


class MockLLMProvider(LLMProviderInterface):
    """Mock LLM provider for testing."""

    def __init__(self):
        self.generate_structured_calls = []
        self.call_count = 0

    async def generate(self, prompt: str) -> str:
        return "mock response"

    async def generate_batch(self, prompts: List[str]) -> List[str]:
        return ["mock response"] * len(prompts)

    async def generate_structured(self, prompt: str, schema):
        self.call_count += 1
        self.generate_structured_calls.append(prompt)
        return RelevanceResponse(
            is_relevant=True,
            score=0.8,
            reasoning="Relevant content",
        )

    def get_provider_name(self) -> str:
        return "mock"

    def get_model_name(self) -> str:
        return "mock-model"


class TestLLMDocumentCompressorCreation:
    """Tests for LLMDocumentCompressor creation."""

    def test_create_compressor_with_provider_and_config(self):
        """Compressor should be created with provider and config."""
        provider = MockLLMProvider()
        config = CompressorConfig()

        compressor = LLMDocumentCompressor(provider, config)

        assert compressor is not None
        assert isinstance(compressor, DocumentCompressorInterface)

    def test_compressor_name_is_llm_document_compressor(self):
        """Compressor name should be 'llm-document-compressor'."""
        provider = MockLLMProvider()
        config = CompressorConfig()

        compressor = LLMDocumentCompressor(provider, config)

        assert compressor.get_compressor_name() == "llm-document-compressor"


class TestLLMDocumentCompressorCompress:
    """Tests for LLMDocumentCompressor.compress method."""

    @pytest.fixture
    def provider(self) -> MockLLMProvider:
        return MockLLMProvider()

    @pytest.fixture
    def config(self) -> CompressorConfig:
        return CompressorConfig(relevance_threshold=0.5)

    @pytest.fixture
    def sample_documents(self) -> List[Document]:
        return [
            Document(page_content="Document 1 content", metadata={"id": "1"}),
            Document(page_content="Document 2 content", metadata={"id": "2"}),
            Document(page_content="Document 3 content", metadata={"id": "3"}),
        ]

    async def test_compress_returns_relevant_documents(
        self,
        provider: MockLLMProvider,
        config: CompressorConfig,
        sample_documents: List[Document],
    ):
        """compress should return documents above threshold."""
        compressor = LLMDocumentCompressor(provider, config)

        results = await compressor.compress(sample_documents, "test query")

        assert isinstance(results, list)
        assert all(isinstance(doc, Document) for doc in results)

    async def test_compress_filters_by_threshold(
        self, config: CompressorConfig, sample_documents: List[Document]
    ):
        """compress should filter documents based on relevance threshold."""
        provider = MockLLMProvider()

        call_count = 0

        async def mock_generate_structured(prompt, schema):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return RelevanceResponse(
                    is_relevant=False, score=0.3, reasoning="Not relevant"
                )
            return RelevanceResponse(
                is_relevant=True, score=0.8, reasoning="Relevant"
            )

        provider.generate_structured = mock_generate_structured

        compressor = LLMDocumentCompressor(provider, config)
        results = await compressor.compress(sample_documents, "test query")

        assert len(results) == 2

    async def test_compress_empty_list_returns_empty(
        self, provider: MockLLMProvider, config: CompressorConfig
    ):
        """compress with empty list should return empty list."""
        compressor = LLMDocumentCompressor(provider, config)

        results = await compressor.compress([], "test query")

        assert results == []


class TestLLMDocumentCompressorCompressWithScores:
    """Tests for LLMDocumentCompressor.compress_with_scores method."""

    @pytest.fixture
    def provider(self) -> MockLLMProvider:
        return MockLLMProvider()

    @pytest.fixture
    def config(self) -> CompressorConfig:
        return CompressorConfig()

    @pytest.fixture
    def sample_documents(self) -> List[Document]:
        return [
            Document(page_content="Doc 1", metadata={"id": "1"}),
            Document(page_content="Doc 2", metadata={"id": "2"}),
        ]

    async def test_compress_with_scores_returns_compressed_documents(
        self,
        provider: MockLLMProvider,
        config: CompressorConfig,
        sample_documents: List[Document],
    ):
        """compress_with_scores should return CompressedDocument objects."""
        compressor = LLMDocumentCompressor(provider, config)

        results = await compressor.compress_with_scores(sample_documents, "test query")

        assert isinstance(results, list)
        assert all(isinstance(doc, CompressedDocument) for doc in results)

    async def test_compress_with_scores_includes_all_documents(
        self,
        provider: MockLLMProvider,
        config: CompressorConfig,
        sample_documents: List[Document],
    ):
        """compress_with_scores should return all documents with scores."""
        compressor = LLMDocumentCompressor(provider, config)

        results = await compressor.compress_with_scores(sample_documents, "test query")

        assert len(results) == len(sample_documents)

    async def test_compress_with_scores_empty_list_returns_empty(
        self, provider: MockLLMProvider, config: CompressorConfig
    ):
        """compress_with_scores with empty list should return empty list."""
        compressor = LLMDocumentCompressor(provider, config)

        results = await compressor.compress_with_scores([], "test query")

        assert results == []


class TestLLMDocumentCompressorParallelProcessing:
    """Tests for parallel processing with Semaphore."""

    @pytest.fixture
    def sample_documents(self) -> List[Document]:
        return [Document(page_content=f"Doc {i}", metadata={"id": str(i)}) for i in range(10)]

    async def test_parallel_processing_uses_semaphore(
        self, sample_documents: List[Document]
    ):
        """Parallel processing should respect max_concurrency with Semaphore."""
        config = CompressorConfig(max_concurrency=3)
        provider = MockLLMProvider()
        concurrent_calls = []
        max_concurrent = 0

        original_generate = provider.generate_structured

        async def tracked_generate(prompt, schema):
            nonlocal max_concurrent
            concurrent_calls.append(1)
            current = len(concurrent_calls)
            if current > max_concurrent:
                max_concurrent = current
            await asyncio.sleep(0.01)
            concurrent_calls.pop()
            return await original_generate(prompt, schema)

        provider.generate_structured = tracked_generate

        compressor = LLMDocumentCompressor(provider, config)
        await compressor.compress(sample_documents, "test query")

        assert max_concurrent <= config.max_concurrency

    async def test_all_documents_processed_in_parallel(
        self, sample_documents: List[Document]
    ):
        """All documents should be processed even with concurrency limit."""
        config = CompressorConfig(max_concurrency=2)
        provider = MockLLMProvider()

        compressor = LLMDocumentCompressor(provider, config)
        results = await compressor.compress_with_scores(sample_documents, "test query")

        assert len(results) == len(sample_documents)
        assert provider.call_count == len(sample_documents)


class TestLLMDocumentCompressorErrorHandling:
    """Tests for error handling in parallel processing."""

    @pytest.fixture
    def sample_documents(self) -> List[Document]:
        return [
            Document(page_content="Doc 1", metadata={"id": "1"}),
            Document(page_content="Doc 2", metadata={"id": "2"}),
            Document(page_content="Doc 3", metadata={"id": "3"}),
        ]

    async def test_individual_failure_does_not_break_batch(
        self, sample_documents: List[Document]
    ):
        """Individual document failures should not break the entire batch."""
        config = CompressorConfig()
        provider = MockLLMProvider()

        call_count = 0

        async def failing_generate(prompt, schema):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("API Error")
            return RelevanceResponse(
                is_relevant=True, score=0.8, reasoning="Relevant"
            )

        provider.generate_structured = failing_generate

        compressor = LLMDocumentCompressor(provider, config)
        results = await compressor.compress(sample_documents, "test query")

        assert len(results) == 2

    async def test_compress_with_scores_handles_failures(
        self, sample_documents: List[Document]
    ):
        """compress_with_scores should handle individual failures gracefully."""
        config = CompressorConfig()
        provider = MockLLMProvider()

        call_count = 0

        async def failing_generate(prompt, schema):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("API Error")
            return RelevanceResponse(
                is_relevant=True, score=0.8, reasoning="Relevant"
            )

        provider.generate_structured = failing_generate

        compressor = LLMDocumentCompressor(provider, config)
        results = await compressor.compress_with_scores(sample_documents, "test query")

        assert len(results) == 2


class TestLLMDocumentCompressorThresholdFiltering:
    """Tests for threshold-based filtering."""

    async def test_documents_below_threshold_excluded(self):
        """Documents with score below threshold should be excluded."""
        config = CompressorConfig(relevance_threshold=0.7)
        provider = MockLLMProvider()

        scores = [0.9, 0.5, 0.8, 0.3, 0.75]
        call_idx = 0

        async def varying_score_generate(prompt, schema):
            nonlocal call_idx
            score = scores[call_idx]
            call_idx += 1
            return RelevanceResponse(
                is_relevant=score >= 0.5,
                score=score,
                reasoning=f"Score: {score}",
            )

        provider.generate_structured = varying_score_generate

        documents = [Document(page_content=f"Doc {i}") for i in range(5)]
        compressor = LLMDocumentCompressor(provider, config)
        results = await compressor.compress(documents, "test query")

        assert len(results) == 3

    async def test_threshold_zero_includes_all_successful(self):
        """Threshold 0.0 should include all successfully evaluated documents."""
        config = CompressorConfig(relevance_threshold=0.0)
        provider = MockLLMProvider()

        async def low_score_generate(prompt, schema):
            return RelevanceResponse(
                is_relevant=False, score=0.1, reasoning="Low score"
            )

        provider.generate_structured = low_score_generate

        documents = [Document(page_content=f"Doc {i}") for i in range(3)]
        compressor = LLMDocumentCompressor(provider, config)
        results = await compressor.compress(documents, "test query")

        assert len(results) == 3

    async def test_threshold_one_filters_all_below_perfect(self):
        """Threshold 1.0 should only include perfect score documents."""
        config = CompressorConfig(relevance_threshold=1.0)
        provider = MockLLMProvider()

        call_idx = 0
        scores = [0.99, 1.0, 0.95]

        async def varying_generate(prompt, schema):
            nonlocal call_idx
            score = scores[call_idx]
            call_idx += 1
            return RelevanceResponse(
                is_relevant=True, score=score, reasoning="Test"
            )

        provider.generate_structured = varying_generate

        documents = [Document(page_content=f"Doc {i}") for i in range(3)]
        compressor = LLMDocumentCompressor(provider, config)
        results = await compressor.compress(documents, "test query")

        assert len(results) == 1

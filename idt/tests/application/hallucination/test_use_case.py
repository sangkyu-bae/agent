"""Tests for HallucinationEvaluatorUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.hallucination.use_case import HallucinationEvaluatorUseCase
from src.domain.hallucination.value_objects import HallucinationEvaluationResult


class TestHallucinationEvaluatorUseCase:
    """Tests for HallucinationEvaluatorUseCase."""

    @pytest.fixture
    def mock_adapter(self) -> AsyncMock:
        """Create a mock adapter."""
        adapter = AsyncMock()
        adapter.evaluate = AsyncMock()
        return adapter

    @pytest.fixture
    def use_case(self, mock_adapter: AsyncMock) -> HallucinationEvaluatorUseCase:
        """Create use case with mocked adapter."""
        return HallucinationEvaluatorUseCase(evaluator_adapter=mock_adapter)

    async def test_evaluate_valid_input_calls_adapter(
        self, use_case: HallucinationEvaluatorUseCase, mock_adapter: AsyncMock
    ) -> None:
        """Evaluate with valid input should call adapter."""
        expected_result = HallucinationEvaluationResult(is_hallucinated=False)
        mock_adapter.evaluate.return_value = expected_result

        result = await use_case.evaluate(
            documents=["Reference document."],
            generation="Generated answer.",
            request_id="test-123"
        )

        mock_adapter.evaluate.assert_called_once_with(
            documents=["Reference document."],
            generation="Generated answer.",
            request_id="test-123"
        )
        assert result == expected_result

    async def test_evaluate_empty_generation_raises_value_error(
        self, use_case: HallucinationEvaluatorUseCase
    ) -> None:
        """Evaluate with empty generation should raise ValueError."""
        with pytest.raises(ValueError, match="Generation and documents are required"):
            await use_case.evaluate(
                documents=["Reference document."],
                generation="",
                request_id="test-456"
            )

    async def test_evaluate_empty_documents_raises_value_error(
        self, use_case: HallucinationEvaluatorUseCase
    ) -> None:
        """Evaluate with empty documents should raise ValueError."""
        with pytest.raises(ValueError, match="Generation and documents are required"):
            await use_case.evaluate(
                documents=[],
                generation="Generated answer.",
                request_id="test-789"
            )

    async def test_evaluate_whitespace_generation_raises_value_error(
        self, use_case: HallucinationEvaluatorUseCase
    ) -> None:
        """Evaluate with whitespace-only generation should raise ValueError."""
        with pytest.raises(ValueError, match="Generation and documents are required"):
            await use_case.evaluate(
                documents=["Reference document."],
                generation="   ",
                request_id="test-whitespace"
            )

    async def test_evaluate_none_generation_raises_value_error(
        self, use_case: HallucinationEvaluatorUseCase
    ) -> None:
        """Evaluate with None generation should raise ValueError."""
        with pytest.raises(ValueError, match="Generation and documents are required"):
            await use_case.evaluate(
                documents=["Reference document."],
                generation=None,
                request_id="test-none"
            )

    async def test_evaluate_returns_adapter_result(
        self, use_case: HallucinationEvaluatorUseCase, mock_adapter: AsyncMock
    ) -> None:
        """Evaluate should return the result from adapter."""
        expected_result = HallucinationEvaluationResult(is_hallucinated=True)
        mock_adapter.evaluate.return_value = expected_result

        result = await use_case.evaluate(
            documents=["Doc 1", "Doc 2"],
            generation="Some hallucinated content.",
            request_id="test-result"
        )

        assert result.is_hallucinated is True
